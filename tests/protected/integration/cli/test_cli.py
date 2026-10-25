import json
import subprocess
import sys
from pathlib import Path

import git
import pytest

RUNNER = """import agent_controls as aa
from agent_controls.processes import BlockWrites

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
aa.run(context)
"""


def run_cli(arguments: list[str], cwd: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agent_controls", *arguments],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "checks.py").write_text(RUNNER, encoding="utf-8")
    return tmp_path


def payload_for(project: Path, path: str) -> str:
    return json.dumps(
        {
            "session_id": "sess-0001-abcd",
            "cwd": project.as_posix(),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": "x"},
        }
    )


def test_run_answers_on_stdout_and_records_the_session(project: Path) -> None:
    completed = run_cli(
        ["run", "checks.py", "--harness", "claude", "--hook", "pre-tool"],
        project,
        payload_for(project, "tests/test_a.py"),
    )

    assert completed.returncode == 0, completed.stderr
    decision = json.loads(completed.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    [session] = [path for path in (project / ".hooks").iterdir() if path.is_dir()]
    assert session.name.endswith("_sess-000")
    assert (session / "main-agent" / "io.json").is_file()


def test_run_reads_the_payload_from_a_file_and_allows_other_paths(project: Path) -> None:
    (project / "payload.json").write_text(payload_for(project, "src/app.py"), encoding="utf-8")

    completed = run_cli(
        [
            "run",
            "checks.py",
            "--harness",
            "claude",
            "--hook",
            "pre-tool",
            "--input",
            "payload.json",
        ],
        project,
    )

    assert (completed.returncode, completed.stdout) == (0, "")


def test_runner_file_without_a_run_call_exits_one(project: Path) -> None:
    (project / "broken.py").write_text("import agent_controls as aa\n", encoding="utf-8")

    completed = run_cli(
        ["run", "broken.py", "--harness", "claude", "--hook", "stop"], project, "{}"
    )

    assert completed.returncode == 1
    assert "did not call agent_controls.run" in completed.stderr


def test_install_writes_the_configuration_with_this_interpreter(project: Path) -> None:
    completed = run_cli(["install", "checks.py", "--target", "copilot-cli"], project)

    assert completed.returncode == 0, completed.stderr
    config = json.loads(
        (project / ".github/hooks/agent-controls-copilot-cli.json").read_text(encoding="utf-8")
    )
    [handler] = config["hooks"]["preToolUse"]
    assert Path(sys.executable).as_posix() in handler["bash"]
    assert "checks.py --harness copilot-cli --hook pre-tool" in handler["bash"]


def test_install_without_target_and_without_a_terminal_fails(project: Path) -> None:
    completed = run_cli(["install", "checks.py"], project)

    assert completed.returncode == 1
    assert "Give --target" in completed.stderr


def test_sessions_lists_a_recorded_session(project: Path) -> None:
    run_cli(
        ["run", "checks.py", "--harness", "claude", "--hook", "pre-tool"],
        project,
        payload_for(project, "tests/test_a.py"),
    )

    completed = run_cli(["sessions"], project)

    assert "session=sess-0001-abcd" in completed.stdout


def test_skills_are_copied_into_the_project(project: Path) -> None:
    completed = run_cli(["skills", "--dest", "agent-skills"], project)

    assert completed.returncode == 0, completed.stderr
    assert (project / "agent-skills" / "agent-controls-processes" / "SKILL.md").is_file()


REVERT_RUNNER = """import agent_controls as aa
from agent_controls.processes import RevertWrites

context = aa.get_current_context()
context.add(RevertWrites(["tests/**"]))
aa.run(context)
"""

COMMAND_RUNNER = """import sys

import agent_controls as aa
from agent_controls.processes import RunCommand

context = aa.get_current_context()
context.add(RunCommand([sys.executable, "check.py"]))
aa.run(context)
"""

CHECK_SCRIPT = """import json
import sys

event = json.load(sys.stdin)
print(f"checked on {event['hook']} for {event['harness']}")
raise SystemExit(1)
"""


def context_of(completed: subprocess.CompletedProcess[str]) -> str:
    assert completed.returncode == 0, completed.stderr
    return str(json.loads(completed.stdout)["hookSpecificOutput"]["additionalContext"])


def test_revert_writes_keeps_its_record_between_two_hook_calls(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    for name in ("tests/test_a.py", "tests/test_b.py", "checks.py", ".gitignore"):
        (tmp_path / name).write_text(
            {"checks.py": REVERT_RUNNER, ".gitignore": ".hooks/\n"}.get(name, "original\n"),
            encoding="utf-8",
        )
    with git.Repo.init(tmp_path) as repo:
        repo.git.add("--all")
        repo.index.commit("first")
    session = {"session_id": "sess-0002-abcd", "cwd": tmp_path.as_posix()}
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n", encoding="utf-8")

    at_start = run_cli(
        ["run", "checks.py", "--harness", "claude", "--hook", "session-start"],
        tmp_path,
        json.dumps(session | {"hook_event_name": "SessionStart"}),
    )
    (tmp_path / "tests" / "test_b.py").write_text("cheat\n", encoding="utf-8")
    after_tool = run_cli(
        ["run", "checks.py", "--harness", "claude", "--hook", "post-tool"],
        tmp_path,
        json.dumps(
            session
            | {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "echo cheat > tests/test_b.py"},
            }
        ),
    )

    assert "tests/test_a.py have uncommitted changes" in context_of(at_start)
    assert "files tests/test_b.py were reverted" in context_of(after_tool)
    assert (tmp_path / "tests" / "test_a.py").read_text(encoding="utf-8") == "work of the user\n"
    assert (tmp_path / "tests" / "test_b.py").read_text(encoding="utf-8") == "original\n"


def test_run_command_pipes_the_event_to_a_real_command(tmp_path: Path) -> None:
    (tmp_path / "checks.py").write_text(COMMAND_RUNNER, encoding="utf-8")
    (tmp_path / "check.py").write_text(CHECK_SCRIPT, encoding="utf-8")

    completed = run_cli(
        ["run", "checks.py", "--harness", "claude", "--hook", "session-start"],
        tmp_path,
        json.dumps(
            {
                "session_id": "sess-0003-abcd",
                "cwd": tmp_path.as_posix(),
                "hook_event_name": "SessionStart",
            }
        ),
    )

    assert context_of(completed).endswith("checked on session-start for claude\n")
