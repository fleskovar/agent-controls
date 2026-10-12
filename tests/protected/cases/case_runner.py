"""Load a hook case folder, run the real pipeline, and produce comparable output.

Nothing here knows pytest. The test file, the `__main__` debug entry point below
and the baseline writer all call the same three functions.

    inputs/case.json    {"harness", "hook", "now"} or {"command": "install", "harness"}
    inputs/runner.py    the runner file that the harness would call
    inputs/stdin.json   the hook payload; "{{root}}" becomes the project folder
    inputs/commit/      optional files that become the one commit of a git repository
                        in the project folder, together with the runner file
    inputs/project/     optional files copied into the project folder next: a seeded
                        .hooks/, or the uncommitted changes on top of inputs/commit/

    outputs/response.json   exit code, stdout document and stderr of one hook call
    outputs/state.json      the newest step in state.json of the agent folder
    outputs/folders.json    every folder under .hooks/, relative and sorted
    outputs/worktree.json   the lines of `git status --short` after the call
    outputs/config.json     the harness configuration file (install cases)

Only the output files that a case folder contains are compared.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import git

from agent_actions.app import install_hooks, parse_payload, run_hook
from agent_actions.harnesses import make_adapter
from agent_actions.model import Harness, Hook
from agent_actions.session import HOOKS_DIR, STATE_FILE, SessionStore
from agent_actions.storage import read_json

CASES_ROOT: Final = Path(__file__).resolve().parent
INPUTS_DIR: Final = "inputs"
OUTPUTS_DIR: Final = "outputs"
COMMIT_DIR: Final = "commit"
PROJECT_DIR: Final = "project"
RUNNER_FILE: Final = "runner.py"
ROOT_PLACEHOLDER: Final = "{{root}}"
INSTALL_PYTHON: Final = "python"
DEFAULT_TIMEOUT: Final = 300
JSON_INDENT: Final = 2


def case_dirs(root: Path = CASES_ROOT) -> list[Path]:
    """Every case folder, sorted. To add a case, add a folder; never edit a test."""
    return sorted(path for path in root.iterdir() if (path / INPUTS_DIR).is_dir())


def read_baselines(case_dir: Path) -> dict[str, Any]:
    """Every baseline document. A baseline can be any JSON value, not only an object."""
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((case_dir / OUTPUTS_DIR).glob("*.json"))
    }


def run_case(case_dir: Path, project: Path) -> dict[str, Any]:
    """The case inputs in a fresh project folder, as the documents its baselines hold."""
    inputs = case_dir / INPUTS_DIR
    spec = read_json(inputs / "case.json")
    project.mkdir(parents=True, exist_ok=True)
    if (inputs / COMMIT_DIR).is_dir():
        _commit(inputs / COMMIT_DIR, inputs / RUNNER_FILE, project)
    if (inputs / PROJECT_DIR).is_dir():
        # copyfile gives each file a new modification time. With the time of the source,
        # git can take a changed file of the same size for the committed one.
        shutil.copytree(
            inputs / PROJECT_DIR, project, copy_function=shutil.copyfile, dirs_exist_ok=True
        )
    shutil.copy(inputs / RUNNER_FILE, project / RUNNER_FILE)
    harness = Harness(spec["harness"])
    documents = (
        _install_documents(project, harness, spec)
        if spec.get("command", "run") == "install"
        else _run_documents(
            project, harness, spec, (inputs / "stdin.json").read_text(encoding="utf-8")
        )
    )
    return _without_absolute_paths(documents, project)


def write_baselines(case_dir: Path, actual: Mapping[str, Any]) -> None:
    """Only for `--write`. Read the diff line by line before you commit it."""
    outputs = case_dir / OUTPUTS_DIR
    outputs.mkdir(exist_ok=True)
    present = {path.name for path in outputs.glob("*.json")}
    for name, document in actual.items():
        if not present or name in present:
            text = json.dumps(document, indent=JSON_INDENT, ensure_ascii=False)
            (outputs / name).write_text(text + "\n", encoding="utf-8")


def _commit(files: Path, runner: Path, project: Path) -> None:
    """A git repository in the project folder. Its one commit holds the files and the runner."""
    shutil.copytree(files, project, copy_function=shutil.copyfile, dirs_exist_ok=True)
    shutil.copy(runner, project / RUNNER_FILE)
    with git.Repo.init(project) as repo:
        repo.git.add("--all")
        repo.index.commit("The last commit")


def _git_status(project: Path) -> list[str]:
    """What differs from the last commit. Empty when the case has no repository."""
    lines: list[str] = []
    if (project / ".git").is_dir():
        with git.Repo(project) as repo:
            lines = repo.git.status("--short", "--untracked-files=all").splitlines()
    return lines


def _install_documents(project: Path, harness: Harness, spec: Mapping[str, Any]) -> dict[str, Any]:
    report = install_hooks(
        project,
        Path(RUNNER_FILE),
        harness,
        spec.get("python", INSTALL_PYTHON),
        spec.get("timeout", DEFAULT_TIMEOUT),
    )
    return {"config.json": read_json(report.config_path)}


def _run_documents(
    project: Path, harness: Harness, spec: Mapping[str, Any], stdin_template: str
) -> dict[str, Any]:
    hook = Hook(spec["hook"])
    now = datetime.fromisoformat(spec["now"])
    payload_text = stdin_template.replace(ROOT_PLACEHOLDER, project.as_posix())

    response = run_hook(project, Path(RUNNER_FILE), harness, hook, payload_text, clock=lambda: now)

    event = make_adapter(harness).parse(hook, parse_payload(payload_text))
    agent_dir = SessionStore(project).agent_dir(event, now)
    hooks_dir = project / HOOKS_DIR
    return {
        "response.json": {
            "exit_code": response.exit_code,
            "stdout": response.stdout,
            "stderr": response.stderr,
        },
        "state.json": _last_step(agent_dir),
        "folders.json": sorted(
            path.relative_to(hooks_dir).as_posix() for path in hooks_dir.rglob("*") if path.is_dir()
        ),
        "worktree.json": _git_status(project),
    }


def _last_step(agent_dir: Path) -> dict[str, Any]:
    """The newest step, without its timestamp and without the inputs that stdin already shows."""
    document = read_json(agent_dir / STATE_FILE)
    step = document[max(document)] if document else {}
    return {
        name: {"state": record["state"], "outputs": record["outputs"]}
        for name, record in step.items()
    }


def _without_absolute_paths(documents: Mapping[str, Any], project: Path) -> dict[str, Any]:
    """Put {{root}} back, so that no baseline holds a temporary folder."""
    text = json.dumps(documents, ensure_ascii=False)
    for form in (str(project), project.as_posix()):
        text = text.replace(json.dumps(form)[1:-1], ROOT_PLACEHOLDER)
    return json.loads(text)


if __name__ == "__main__":
    # Debug entry point, with no pytest frames on the stack:
    #     python tests/protected/cases/case_runner.py <case-name>
    # Put a breakpoint on the `run_case` line below and step in.
    # Add --write to rewrite the baselines of that case.
    case_name = sys.argv[1] if len(sys.argv) > 1 else case_dirs()[0].name
    case_folder = CASES_ROOT / case_name
    with tempfile.TemporaryDirectory() as folder:
        result = run_case(case_folder, Path(folder) / PROJECT_DIR)
    if "--write" in sys.argv[2:]:
        write_baselines(case_folder, result)
        print(f"Wrote the baselines of {case_name}.")
    else:
        print(json.dumps(result, indent=JSON_INDENT, ensure_ascii=False))
