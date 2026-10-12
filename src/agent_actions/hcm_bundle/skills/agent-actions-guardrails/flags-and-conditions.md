# Checks that depend on the context

A basic check does the same thing on each hook call. The tools on this page let a
check react to the session: to the files that changed, to an earlier tool call, to
an earlier session, or to a decision of a person.

| Tool | Purpose |
| --- | --- |
| `context.flags` | A dict of named JSON values for all sessions of the project. File: `.hooks/flags.json`. |
| `context.session_flags` | The same for one session. The main agent and its subagents share it. File: `.hooks/<session>/flags.json`. |
| `context.add(process, when=...)` | Runs the process only when a function of the hook event returns a true value. |
| `SetFlag(flags, flag, value)` | A process that sets a flag on the hooks in `on`. |
| `git_snapshot` | A value for `SetFlag`: the state of the git work tree. |
| `changed_paths(root, snapshot, patterns)` | The files that changed after a snapshot. |
| `on_changed_paths(flags, patterns)` | A `command_runner` that gives a command only the changed files. |
| `clear_on_pass(flags, flag)` | A `command_runner` that deletes a flag when the command passes. |

Import them from `agent_actions.processes`. The reference page of the
`agent-actions-processes` skill has each parameter.

## Before you start

- Add `.hooks/flags.json` to `.gitignore`. Without it, git reports the file as a
  change, and a `RevertWrites` that covers `.hooks` deletes the flags.
- `git_snapshot` and `changed_paths` need a git repository with one commit or more.
- Use `when`, not an `if` around `context.add`. `install` loads the runner file
  with empty flags. A process in an `if` on a flag is not added, and its hook is
  not registered.
- Run `agent_actions install` again after you add a process. A new process can
  use a hook that the other processes do not use.

## Select the scope of a flag

| The value is for | Use | Example |
| --- | --- | --- |
| One process of one agent | `__state__` of the process, not a flag | A retry count. |
| The processes of one session | `context.session_flags` | A baseline, "the agent read the guide". |
| Each later session | `context.flags` | "The tests are due", a freeze by a person. |

## Select the baseline

A snapshot in a flag is a baseline. The hook that saves it sets its lifetime.

| The changes of | Save the snapshot with |
| --- | --- |
| The session | `SetFlag(session, "baseline", git_snapshot, keep=True)` |
| One prompt | `SetFlag(session, "turn", git_snapshot, on=[aa.Hook.USER_PROMPT])` |
| The time after an event in an earlier session | A snapshot in `context.flags`, saved when that event occurs. |

- `keep=True` keeps the first value. A harness can fire `session-start` again in
  one session, for example after a compaction.
- A file with uncommitted changes from before the snapshot is not a change. The
  agent is not blamed for the work of the user.
- The comparison reads git. Thus it finds a change from a shell command too.
- Without a snapshot, each uncommitted change counts. A check then reads more
  files, not fewer.

## Pattern 1: check only the files that the session changed

Use it when the linter is slow, or when the project has old problems that are
not the task of the agent.

```python
import sys

import agent_actions as aa
from agent_actions.processes import (
    LoopGuard,
    RequireCommand,
    SetFlag,
    changed_paths,
    git_snapshot,
    on_changed_paths,
)

PYTHON = sys.executable
TESTS = [PYTHON, "-m", "pytest", "-q"]
SOURCES = ["src/**", "tests/**"]

context = aa.get_current_context()
session = context.session_flags

context.add(SetFlag(session, "baseline", git_snapshot, keep=True))

# The tool accepts file paths: `{paths}` becomes the changed files that match.
context.add(
    LoopGuard(
        RequireCommand(
            [PYTHON, "-m", "ruff", "check", "{paths}"],
            name="lint",
            command_runner=on_changed_paths(session, ["*.py"]),
        )
    )
)

# The tool reads the full project: run it only when a source file changed.
context.add(
    LoopGuard(RequireCommand(TESTS, name="tests")),
    when=lambda event: changed_paths(event.root, session.get("baseline"), SOURCES),
)

aa.run(context)
```

- A session that changes only documentation runs no command.
- When no file matches, the command with `{paths}` does not run, and it passes.
- Deleted files are not in `{paths}`.
- For a tool that accepts no file paths, for example `dotnet build`, use the
  second form.
- For a subagent, add `on=[aa.Hook.STOP, aa.Hook.SUBAGENT_STOP]` to the command
  process. The subagent uses the baseline of its session.

## Pattern 2: a debt for the next session

Use it when the agent can stop before a check passes: `LoopGuard` released the
stop, or the user closed the session. The next session must not start clean.

```python
import agent_actions as aa
from agent_actions.processes import AddContext, LoopGuard, RequireTests, SetFlag, clear_on_pass
from agent_actions.processes.paths import matching_pattern, relative_path

SOURCES = ["src/**", "tests/**"]
NOTE = (
    "An earlier session changed the source code and ended before the tests passed. "
    "Run the tests first, and make them pass before you start other work."
)

context = aa.get_current_context()
flags = context.flags


def edits_a_source_file(event: aa.HookInput) -> bool:
    tool = event.tool
    return (
        tool is not None
        and tool.kind is aa.ToolKind.WRITE
        and any(
            matching_pattern(relative_path(path, event.cwd, event.root), SOURCES)
            for path in tool.paths
        )
    )


context.add(SetFlag(flags, "tests-due", on=[aa.Hook.POST_TOOL]), when=edits_a_source_file)
context.add(
    LoopGuard(RequireTests(command_runner=clear_on_pass(flags, "tests-due"))),
    when=lambda _: flags.get("tests-due"),
)
context.add(AddContext(NOTE, name="tests-due-note"), when=lambda _: flags.get("tests-due"))

aa.run(context)
```

- The flag is set by an edit, and deleted only by a pass of the tests.
- A session that changes no source file runs no tests, unless the flag is there.
- The condition reads the tool call. It is fast, but it does not see a change
  from a shell command. For that, use `changed_paths` as in pattern 1.
- For a different test tool, use `RequireCommand(TESTS, command_runner=...)`.
- Copilot CLI has no context channel on `session-start`. Remove the note there.

## Pattern 3: a gate that an event opens

Use it when the agent must do one thing before a different thing: read a guide
before an edit, run a migration check before a change of the schema.

```python
import agent_actions as aa
from agent_actions.processes import BlockWrites, SetFlag
from agent_actions.processes.paths import matching_pattern, relative_path

GUIDE = "docs/architecture.md"
GUARDED = ["src/**"]

context = aa.get_current_context()
session = context.session_flags


def reads_the_guide(event: aa.HookInput) -> bool:
    tool = event.tool
    return (
        tool is not None
        and tool.kind is aa.ToolKind.READ
        and any(
            matching_pattern(relative_path(path, event.cwd, event.root), [GUIDE])
            for path in tool.paths
        )
    )


context.add(SetFlag(session, "guide-read", on=[aa.Hook.POST_TOOL]), when=reads_the_guide)
context.add(
    BlockWrites(
        GUARDED,
        reason=f"Read {GUIDE} first. It gives the rules for a change of these files.",
        name="read-before-write",
    ),
    when=lambda _: not session.get("guide-read"),
)

aa.run(context)
```

- One event opens the gate for the full session, also for the subagents.
- The reason must name the action that opens the gate. Without it, the agent
  cannot continue.
- The same shape works with other events. A stop of a `code-reviewer` subagent
  can set a flag that the stop of the main agent needs:
  `when=lambda event: event.agent_type == "code-reviewer"` on
  `aa.Hook.SUBAGENT_STOP`.

## Pattern 4: a limit for one prompt

Use it when a small request must not grow into a large change without the user.
The harness asks the user before the write that goes past the limit.

```python
from collections.abc import Mapping
from typing import Any

import agent_actions as aa
from agent_actions.processes import SetFlag, changed_paths, git_snapshot

MAX_FILES = 10


class ChangeBudget(aa.PreToolProcess):
    """Asks the user before a write when the current prompt changed `max_files` files or more."""

    def __init__(self, flags: Mapping[str, Any], max_files: int, *, name: str = "") -> None:
        self.flags = flags
        self.max_files = max_files
        self.name = name

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        changed = changed_paths(event.root, self.flags.get("turn"))
        if len(changed) < self.max_files:
            return aa.allow(f"{len(changed)} of {self.max_files} files changed.")
        return aa.ask(
            f"This prompt changed {len(changed)} files, and the limit is {self.max_files}. "
            "Approve the write only if the task needs a change of this size."
        )


context = aa.get_current_context()
session = context.session_flags

context.add(SetFlag(session, "turn", git_snapshot, on=[aa.Hook.USER_PROMPT]))
context.add(
    ChangeBudget(session, MAX_FILES),
    when=lambda event: event.tool is not None and event.tool.kind is aa.ToolKind.WRITE,
)

aa.run(context)
```

- The snapshot has no `keep`. Each prompt replaces it, so each prompt starts a
  new count.
- The condition keeps git out of each read and each search.
- `ask` is possible only on `pre-tool`. For a hard limit, return `aa.block`.

## Pattern 5: files that must change together

Use it for a rule such as "a change of the API needs a change of the
documentation". The stop is blocked while one group changed and its paired group
did not.

```python
context.add(SetFlag(session, "baseline", git_snapshot, keep=True))
context.add(
    LoopGuard(
        RequirePairedChange(
            session,
            ["pyproject.toml", "requirements*.txt"],
            ["CHANGELOG.md"],
            "Add the dependency change to the changelog.",
            name="dependencies-need-changelog",
        )
    )
)
```

`RequirePairedChange` is a process of 15 lines. Its code and its test are in the
`agent-actions-processes` skill, in the section about flags. Keep the
`LoopGuard`: some changes need no paired change, and the agent then reports that.

## Pattern 6: switches that a person sets

Use it when a person must change the behaviour of the agents quickly. A person
edits `.hooks/flags.json`. The next hook call uses the new value, in each open
session. `agent_actions install` is not necessary.

```json
{
  "freeze": "Release 2.4 is in review until Friday.",
  "note": "Do not use the billing sandbox this week. Its data is wrong."
}
```

```python
import agent_actions as aa
from agent_actions.processes import AddContext, BlockWrites

context = aa.get_current_context()
flags = context.flags

FLAG_FILES = [".hooks/flags.json", ".hooks/*/flags.json"]

context.add(BlockWrites(FLAG_FILES, check_shell=True, name="protect-flags"))
context.add(
    BlockWrites(
        ["src/**"],
        reason=f"The source code is frozen: {flags.get('freeze')} Tell the user, and wait.",
        name="freeze",
    ),
    when=lambda _: flags.get("freeze"),
)
context.add(
    AddContext(f"A note from the team: {flags.get('note')}", name="note"),
    when=lambda _: flags.get("note"),
)

aa.run(context)
```

- The runner file runs again at each hook call, after the flags are loaded.
  Thus the value of a flag can be a part of a reason or of a context.
- Tell the user the names of the flags and the file. The user sets them, not you.
- Copilot CLI has no context channel on `session-start`. Remove the note there.

## Protect the flags

A flag is a file. An agent that changes it can open a gate or delete a debt.

- Add the `protect-flags` process of pattern 6. It blocks the write tools on the
  flag files, and each shell command that mentions `flags.json`.
- `RevertWrites` cannot protect a flag file, because git ignores it.
- Do not set or delete a flag for the user to make a check pass. Tell the user
  which flag blocks, and why.

## More patterns

Each one is a small change of a pattern above.

| Goal | Shape |
| --- | --- |
| No stop before a review | A `SetFlag` on `subagent-stop` for the reviewer agent type, and a stop process that blocks while the flag is not set and source files changed. |
| Handover between sessions | At each stop, save `changed_paths(...)` in a project flag. At the next session start, `AddContext` gives the list. |
| The changes after the last pass of the tests | A `command_runner` that saves a snapshot in a project flag when the command passes. |
| A slow scan one time for each day | A project flag with the date of the last scan, and `when` that compares it with the date of today. |
| A strict mode from the prompt | A `SetFlag` on `user-prompt` with `when=lambda event: "#careful" in (event.prompt or "")`, and stricter processes with `when` on that flag. |

## Find the cause of a problem

| File | Content |
| --- | --- |
| `.hooks/flags.json` | The project flags, as they are now. |
| `.hooks/<session>/flags.json` | The session flags, as they are now. |
| `.hooks/<session>/<agent>/log.txt` | One line for each skipped process, and one for each hook call that changed a flag. |

- A process with a false condition has a `skipped` line in `log.txt`, and no
  record in `state.json`.
- A condition that raises an exception blocks where the hook can block.
- Two parallel hook calls can change two different flags. When they change the
  same flag, the last call wins.
- The troubleshooting page of the `agent-actions-setup` skill has more symptoms.
