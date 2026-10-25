import json
from pathlib import Path

import git
import pytest
from builders import an_event

from agent_controls.harnesses import make_adapter
from agent_controls.model import Harness, Hook, HookInput, allow
from agent_controls.processes import RevertWrites
from agent_controls.processes.paths import REVERT_WARNING, START_WARNING
from agent_controls.runtime import compatibility_problems


@pytest.fixture
def repo(tmp_path: Path) -> git.Repo:
    """A repository with one commit: two protected test files and an application file."""
    repo = git.Repo.init(tmp_path)
    (tmp_path / "tests").mkdir()
    for name in ("tests/test_a.py", "tests/test_b.py", "app.py"):
        (tmp_path / name).write_text("original\n")
    repo.index.add(["tests/test_a.py", "tests/test_b.py", "app.py"])
    repo.index.commit("first")
    return repo


def event_in(root: Path, hook: Hook = Hook.POST_TOOL) -> HookInput:
    return an_event(hook, cwd=str(root), root=str(root))


def started(process: RevertWrites, root: Path) -> RevertWrites:
    """The process after the session-start hook, with its state as the engine restores it."""
    process.load_state({})
    process.run(event_in(root, Hook.SESSION_START))
    return process


def test_tool_changes_to_protected_paths_are_reverted(repo: git.Repo, tmp_path: Path) -> None:
    process = started(RevertWrites(["tests/**"]), tmp_path)
    (tmp_path / "tests" / "test_a.py").write_text("cheat\n")
    (tmp_path / "tests" / "test_b.py").unlink()
    (tmp_path / "tests" / "test_new.py").write_text("new\n")
    (tmp_path / "tests" / "test_staged.py").write_text("new\n")
    repo.index.add(["tests/test_staged.py"])
    (tmp_path / "app.py").write_text("changed\n")

    result = process.run(event_in(tmp_path))

    names = "tests/test_a.py, tests/test_b.py, tests/test_new.py, tests/test_staged.py"
    assert result == allow(context=REVERT_WARNING.format(names=names))
    assert (tmp_path / "tests" / "test_a.py").read_text() == "original\n"
    assert (tmp_path / "tests" / "test_b.py").read_text() == "original\n"
    assert not (tmp_path / "tests" / "test_new.py").exists()
    assert not (tmp_path / "tests" / "test_staged.py").exists()
    assert repo.git.status("--porcelain") == " M app.py"


def test_changes_from_before_the_session_are_flagged_and_never_reverted(
    repo: git.Repo, tmp_path: Path
) -> None:
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    process = RevertWrites(["tests/**"])
    process.load_state({})

    at_start = process.run(event_in(tmp_path, Hook.SESSION_START))
    (tmp_path / "tests" / "test_b.py").write_text("cheat\n")
    after_tool = process.run(event_in(tmp_path))

    assert at_start == allow(context=START_WARNING.format(names="tests/test_a.py"))
    assert after_tool == allow(context=REVERT_WARNING.format(names="tests/test_b.py"))
    assert (tmp_path / "tests" / "test_a.py").read_text() == "work of the user\n"
    assert process.dump_state() == {"unresolved": ["tests/test_a.py"]}


def test_a_flagged_path_is_protected_again_after_the_user_commits_it(
    repo: git.Repo, tmp_path: Path
) -> None:
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    process = started(RevertWrites(["tests/**"]), tmp_path)
    repo.index.add(["tests/test_a.py"])
    repo.index.commit("second")
    process.run(event_in(tmp_path))
    (tmp_path / "tests" / "test_a.py").write_text("cheat\n")

    process.run(event_in(tmp_path))

    assert (tmp_path / "tests" / "test_a.py").read_text() == "work of the user\n"


def test_first_tool_call_without_a_start_hook_flags_and_reverts_nothing(
    repo: git.Repo, tmp_path: Path
) -> None:
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    process = RevertWrites(["tests/**"], on=[Hook.POST_TOOL])
    process.load_state({})

    result = process.run(event_in(tmp_path))

    assert result == allow(context=START_WARNING.format(names="tests/test_a.py"))
    assert (tmp_path / "tests" / "test_a.py").read_text() == "work of the user\n"


def test_a_project_root_below_the_repository_root_keeps_its_own_patterns(
    repo: git.Repo, tmp_path: Path
) -> None:
    process = started(RevertWrites(["test_a.py"]), tmp_path / "tests")
    (tmp_path / "tests" / "test_a.py").write_text("cheat\n")
    (tmp_path / "tests" / "test_b.py").write_text("not protected\n")

    process.run(event_in(tmp_path / "tests"))

    assert (tmp_path / "tests" / "test_a.py").read_text() == "original\n"
    assert (tmp_path / "tests" / "test_b.py").read_text() == "not protected\n"


def test_changes_outside_the_protected_paths_get_no_warning(repo: git.Repo, tmp_path: Path) -> None:
    process = started(RevertWrites(["tests/**"]), tmp_path)
    (tmp_path / "app.py").write_text("changed\n")

    assert process.run(event_in(tmp_path)) == allow()
    assert (tmp_path / "app.py").read_text() == "changed\n"


@pytest.mark.parametrize("hook", [Hook.SESSION_START, Hook.SUBAGENT_START])
def test_each_start_hook_flags_the_changed_protected_paths(
    repo: git.Repo, tmp_path: Path, hook: Hook
) -> None:
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    (tmp_path / "tests" / "test_new.py").write_text("work of the user\n")
    (tmp_path / "app.py").write_text("changed\n")
    process = RevertWrites(["tests/**"])
    process.load_state({})

    result = process.run(event_in(tmp_path, hook))

    names = "tests/test_a.py, tests/test_new.py"
    assert result == allow(context=START_WARNING.format(names=names))
    assert process.dump_state() == {"unresolved": ["tests/test_a.py", "tests/test_new.py"]}


def test_start_on_a_clean_work_tree_gives_no_warning(repo: git.Repo, tmp_path: Path) -> None:
    process = RevertWrites(["tests/**"])
    process.load_state({})

    assert process.run(event_in(tmp_path, Hook.SESSION_START)) == allow()
    assert process.dump_state() == {"unresolved": []}


def test_a_later_start_hook_replaces_the_recorded_paths(repo: git.Repo, tmp_path: Path) -> None:
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    process = started(RevertWrites(["tests/**"]), tmp_path)
    repo.index.add(["tests/test_a.py"])
    repo.index.commit("second")
    (tmp_path / "tests" / "test_b.py").write_text("more work of the user\n")

    result = process.run(event_in(tmp_path, Hook.SESSION_START))

    assert result == allow(context=START_WARNING.format(names="tests/test_b.py"))
    assert process.dump_state() == {"unresolved": ["tests/test_b.py"]}


def test_recorded_paths_come_back_from_the_saved_state(repo: git.Repo, tmp_path: Path) -> None:
    """Each hook call is a new Python process. The record must pass through state.json."""
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    saved = json.loads(json.dumps(started(RevertWrites(["tests/**"]), tmp_path).dump_state()))
    (tmp_path / "tests" / "test_b.py").write_text("cheat\n")
    process = RevertWrites(["tests/**"])
    process.load_state(saved)

    result = process.run(event_in(tmp_path))

    assert result == allow(context=REVERT_WARNING.format(names="tests/test_b.py"))
    assert (tmp_path / "tests" / "test_a.py").read_text() == "work of the user\n"
    assert (tmp_path / "tests" / "test_b.py").read_text() == "original\n"


def test_a_new_file_from_before_the_session_is_not_deleted(repo: git.Repo, tmp_path: Path) -> None:
    (tmp_path / "tests" / "test_draft.py").write_text("work of the user\n")
    process = started(RevertWrites(["tests/**"]), tmp_path)

    assert process.run(event_in(tmp_path)) == allow()
    assert (tmp_path / "tests" / "test_draft.py").read_text() == "work of the user\n"


def test_a_protected_file_that_was_moved_away_is_restored(repo: git.Repo, tmp_path: Path) -> None:
    process = started(RevertWrites(["tests/**"]), tmp_path)
    repo.git.mv("tests/test_a.py", "moved.py")

    result = process.run(event_in(tmp_path))

    assert result == allow(context=REVERT_WARNING.format(names="tests/test_a.py"))
    assert (tmp_path / "tests" / "test_a.py").read_text() == "original\n"
    assert (tmp_path / "moved.py").exists()


def test_a_file_name_with_pattern_characters_reverts_that_file_only(
    repo: git.Repo, tmp_path: Path
) -> None:
    """Git reads `[a]` in a pathspec as a character class, which also matches `test_a.py`.

    Without literal pathspecs, the revert of `test_[a].py` discards the flagged
    work of the user in `test_a.py`, and the delete of `draft_[a].py` deletes `draft_a.py`.
    """
    (tmp_path / "tests" / "test_[a].py").write_text("original\n")
    repo.index.add(["tests/test_[a].py"])
    repo.index.commit("second")
    (tmp_path / "tests" / "test_a.py").write_text("work of the user\n")
    (tmp_path / "tests" / "draft_a.py").write_text("work of the user\n")
    process = started(RevertWrites(["tests/**"]), tmp_path)
    (tmp_path / "tests" / "test_[a].py").write_text("cheat\n")
    (tmp_path / "tests" / "draft_[a].py").write_text("cheat\n")

    result = process.run(event_in(tmp_path))

    names = "tests/draft_[a].py, tests/test_[a].py"
    assert result == allow(context=REVERT_WARNING.format(names=names))
    assert (tmp_path / "tests" / "test_[a].py").read_text() == "original\n"
    assert not (tmp_path / "tests" / "draft_[a].py").exists()
    assert (tmp_path / "tests" / "test_a.py").read_text() == "work of the user\n"
    assert (tmp_path / "tests" / "draft_a.py").read_text() == "work of the user\n"


def test_files_that_git_ignores_are_not_checked(repo: git.Repo, tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.log\n")
    repo.index.add([".gitignore"])
    repo.index.commit("second")
    process = started(RevertWrites(["tests/**"]), tmp_path)
    (tmp_path / "tests" / "run.log").write_text("output of a test run\n")

    assert process.run(event_in(tmp_path)) == allow()
    assert (tmp_path / "tests" / "run.log").exists()


def test_one_pattern_can_be_a_string_and_the_name_sets_the_label() -> None:
    process = RevertWrites("tests/**", name="frozen-tests")

    assert process.patterns == ("tests/**",)
    assert process.label == "frozen-tests"


def test_default_hooks_are_the_start_hooks_and_post_tool() -> None:
    assert RevertWrites(["tests/**"]).hooks == (
        Hook.SESSION_START,
        Hook.SUBAGENT_START,
        Hook.POST_TOOL,
    )


@pytest.mark.parametrize(
    ("harness", "process", "accepted"),
    [
        (Harness.CLAUDE, RevertWrites(["tests/**"]), True),
        (Harness.VSCODE, RevertWrites(["tests/**"]), True),
        (Harness.COPILOT_CLI, RevertWrites(["tests/**"]), False),
        (Harness.COPILOT_CLI, RevertWrites(["tests/**"], on=[Hook.POST_TOOL]), True),
        (Harness.CLAUDE, RevertWrites(["tests/**"], on=[Hook.STOP]), False),
    ],
    ids=[
        "claude_default_hooks",
        "vscode_default_hooks",
        "copilot_cli_has_no_start_context",
        "copilot_cli_post_tool_only",
        "stop_has_no_context_channel",
    ],
)
def test_harness_accepts_the_process_only_where_the_warning_can_arrive(
    harness: Harness, process: RevertWrites, accepted: bool
) -> None:
    assert (compatibility_problems(process, make_adapter(harness)) == []) is accepted
