"""The runner files in examples/ load, and each one does what its docstring tells."""

import json
import re
import shutil
import textwrap
from pathlib import Path
from typing import Any

import git
import pytest

from agent_actions.app import install_hooks, run_hook
from agent_actions.harnesses import make_adapter
from agent_actions.hcm import BUNDLE_DIR
from agent_actions.model import Harness, Hook
from agent_actions.runtime import load_runner

EXAMPLES = Path(__file__).parents[2] / "examples"
RUNNER = "checks.py"


def project(tmp_path: Path, example: str, *, commit: bool = False) -> Path:
    """A project with one example as its runner file, and with one git commit on request."""
    shutil.copy(EXAMPLES / f"{example}.py", tmp_path / RUNNER)
    if commit:
        (tmp_path / ".gitignore").write_text(".hooks/\n.ruff_cache/\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
        repo = git.Repo.init(tmp_path)
        repo.index.add([RUNNER, ".gitignore", "pyproject.toml"])
        repo.index.commit("first")
        repo.close()
    return tmp_path


def call(root: Path, hook: Hook, session: str = "one", **payload: Any) -> dict[str, Any]:
    """The stdout document of one Claude Code hook call. An empty dict means no objection."""
    text = json.dumps({"session_id": session, **payload})
    response = run_hook(root, Path(RUNNER), Harness.CLAUDE, hook, text)
    assert response.exit_code == 0, response.stderr
    return dict(response.stdout or {})


def tool(name: str, path: str) -> dict[str, Any]:
    return {"tool_name": name, "tool_input": {"file_path": path}}


def decision(document: dict[str, Any]) -> str | None:
    return document.get("hookSpecificOutput", {}).get("permissionDecision")


def reason(document: dict[str, Any]) -> str:
    return str(document.get("hookSpecificOutput", {}).get("permissionDecisionReason"))


def context_text(document: dict[str, Any]) -> str | None:
    return document.get("hookSpecificOutput", {}).get("additionalContext")


@pytest.mark.parametrize("example", sorted(path.name for path in EXAMPLES.glob("*.py")))
def test_each_example_loads_and_installs_for_claude(example: str, tmp_path: Path) -> None:
    hooks = load_runner(EXAMPLES / example, make_adapter(Harness.CLAUDE), None, None).hooks()

    shutil.copy(EXAMPLES / example, tmp_path / RUNNER)
    assert hooks
    assert install_hooks(tmp_path, Path(RUNNER), Harness.CLAUDE, "python").hooks == hooks


def test_checks_on_changed_files_reads_only_the_files_of_the_session(tmp_path: Path) -> None:
    root = project(tmp_path, "checks_on_changed_files", commit=True)
    (root / "old.py").write_text("import os\n")  # a lint problem from before the session
    call(root, Hook.SESSION_START)

    (root / "README.md").write_text("documentation\n")
    assert call(root, Hook.STOP) == {}

    (root / "new.py").write_text("import sys\n")
    blocked = call(root, Hook.STOP)

    assert blocked["decision"] == "block"
    assert "[Limit(lint)]" in blocked["reason"]
    assert "new.py" in blocked["reason"]
    assert "old.py" not in blocked["reason"]


def test_tests_due_across_sessions_gives_the_next_session_a_note(tmp_path: Path) -> None:
    root = project(tmp_path, "tests_due_across_sessions")
    assert context_text(call(root, Hook.SESSION_START)) is None

    call(root, Hook.POST_TOOL, **tool("Edit", "README.md"))
    assert not (root / ".hooks/flags.json").exists()
    call(root, Hook.POST_TOOL, **tool("Edit", "src/pricing.py"))

    assert json.loads((root / ".hooks/flags.json").read_text("utf-8")) == {"tests-due": True}
    note = context_text(call(root, Hook.SESSION_START, session="two"))
    assert note is not None and "Run the tests first" in note


def test_read_before_write_opens_the_gate_after_a_read_of_the_guide(tmp_path: Path) -> None:
    root = project(tmp_path, "read_before_write")
    edit = tool("Edit", str(root / "src/pricing.py"))

    denied = call(root, Hook.PRE_TOOL, **edit)
    assert decision(denied) == "deny"
    assert "Read docs/architecture.md first" in reason(denied)

    call(root, Hook.POST_TOOL, **tool("Read", str(root / "README.md")))
    assert decision(call(root, Hook.PRE_TOOL, **edit)) == "deny"

    call(root, Hook.POST_TOOL, **tool("Read", str(root / "docs/architecture.md")))
    assert call(root, Hook.PRE_TOOL, **edit) == {}
    assert decision(call(root, Hook.PRE_TOOL, session="two", **edit)) == "deny"


def test_change_budget_asks_the_user_at_the_limit_and_a_new_prompt_resets_it(
    tmp_path: Path,
) -> None:
    root = project(tmp_path, "change_budget_per_prompt", commit=True)
    write = tool("Write", "notes.md")
    call(root, Hook.USER_PROMPT, prompt="rename one variable")

    for number in range(9):
        (root / f"file_{number}.py").write_text("x = 1\n")
    assert call(root, Hook.PRE_TOOL, **write) == {}

    (root / "file_9.py").write_text("x = 1\n")
    asked = call(root, Hook.PRE_TOOL, **write)
    assert decision(asked) == "ask"
    assert "changed 10 files" in reason(asked)
    assert call(root, Hook.PRE_TOOL, **tool("Read", "notes.md")) == {}

    call(root, Hook.USER_PROMPT, prompt="continue")
    assert call(root, Hook.PRE_TOOL, **write) == {}


def test_paired_changes_blocks_the_stop_until_the_paired_file_changes(tmp_path: Path) -> None:
    root = project(tmp_path, "paired_changes", commit=True)
    call(root, Hook.SESSION_START)
    assert call(root, Hook.STOP) == {}

    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\ndependencies = ['x']\n")
    blocked = call(root, Hook.STOP)
    assert blocked["decision"] == "block"
    assert "You changed pyproject.toml, but no file in CHANGELOG.md" in blocked["reason"]

    (root / "CHANGELOG.md").write_text("- Added the dependency x.\n")
    assert call(root, Hook.STOP) == {}


def test_human_switches_follow_the_flag_file_without_a_new_install(tmp_path: Path) -> None:
    root = project(tmp_path, "human_switches")
    edit = tool("Edit", "src/pricing.py")
    assert call(root, Hook.PRE_TOOL, **edit) == {}
    assert context_text(call(root, Hook.SESSION_START)) is None

    (root / ".hooks/flags.json").write_text(
        '{"freeze": "Release 2.4 is in review.", "note": "Do not use the billing sandbox."}'
    )

    frozen = call(root, Hook.PRE_TOOL, **edit)
    assert decision(frozen) == "deny"
    assert "The source code is frozen: Release 2.4 is in review." in reason(frozen)
    note = context_text(call(root, Hook.SESSION_START))
    assert note == "A note from the team: Do not use the billing sandbox."

    tamper = {"tool_name": "Bash", "tool_input": {"command": "echo {} > .hooks/flags.json"}}
    assert decision(call(root, Hook.PRE_TOOL, **tamper)) == "deny"


# --- the runner files in the pages of the hcm bundle ----------------------------------

FENCED_PYTHON = re.compile(r"^[ \t]*```python\n(.*?)^[ \t]*```", re.DOTALL | re.MULTILINE)


def bundle_runner_files() -> dict[str, str]:
    """Each fenced Python block in the bundle that is a complete runner file."""
    return {
        f"{page.parent.name}/{page.name}#{number}": textwrap.dedent(block)
        for page in sorted(BUNDLE_DIR.rglob("*.md"))
        for number, block in enumerate(FENCED_PYTHON.findall(page.read_text("utf-8")), start=1)
        if "aa.run(context)" in block
    }


@pytest.mark.parametrize("label", bundle_runner_files())
def test_each_runner_file_in_the_bundle_pages_loads_for_claude(label: str, tmp_path: Path) -> None:
    runner = tmp_path / RUNNER
    runner.write_text(bundle_runner_files()[label], encoding="utf-8")

    assert load_runner(runner, make_adapter(Harness.CLAUDE), None, None).hooks()


def test_the_bundle_shows_each_pattern_of_the_examples() -> None:
    page = (BUNDLE_DIR / "skills/agent-actions-guardrails/flags-and-conditions.md").read_text(
        "utf-8"
    )
    skill = (BUNDLE_DIR / "skills/agent-actions-processes/SKILL.md").read_text("utf-8")

    assert [f"## Pattern {number}:" in page for number in range(1, 7)] == [True] * 6
    assert "class ChangeBudget(aa.PreToolProcess):" in page
    assert "class RequirePairedChange(aa.StopProcess):" in skill


def test_exit_strategies_ask_the_user_and_release_the_stop_with_a_review_note(
    tmp_path: Path,
) -> None:
    root = project(tmp_path, "exit_strategies")
    write = tool("Write", str(root / "migrations/0002.sql"))
    assert [decision(call(root, Hook.PRE_TOOL, **write)) for _ in range(3)] == [
        "deny",
        "deny",
        "ask",
    ]

    (root / "test_pricing.py").write_text("def test_total():\n    assert False\n")
    stops = [call(root, Hook.STOP) for _ in range(6)]

    assert [stop.get("decision") for stop in stops] == [*["block"] * 5, None]
    assert "Try a different approach" in stops[4]["reason"]
    assert json.loads((root / ".hooks/flags.json").read_text("utf-8")) == {"needs-review": True}
    note = context_text(call(root, Hook.SESSION_START, session="two"))
    assert note is not None and "the user must review it" in note

    call(root, Hook.STOP, session="three")
    call(root, Hook.USER_PROMPT, session="three", prompt="try a mock")
    assert "Count: 1 of 5 in a row" in call(root, Hook.STOP, session="three")["reason"]
