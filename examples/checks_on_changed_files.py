"""Checks that follow the changes of the session.

- Session start: save the state of the git work tree as the baseline.
- Stop: the format check and the linter read only the Python files that changed
  after the baseline.
- Stop: the tests run only when a source file changed after the baseline.

A session that changes only documentation runs no command. A lint problem in a
file that the session did not change does not block the agent. A subagent uses the
baseline of its session, so the same rules apply to its stop.

The comparison reads git. Thus it also finds a change that a shell command made.
"""

import sys

import agent_actions as aa
from agent_actions.processes import (
    Limit,
    RequireCommand,
    RequireTests,
    SetFlag,
    changed_paths,
    git_snapshot,
    on_changed_paths,
)

PYTHON = sys.executable
SOURCES = ["src/**", "tests/**"]
STOPS = [aa.Hook.STOP, aa.Hook.SUBAGENT_STOP]

context = aa.get_current_context()
session = context.session_flags

# `keep`: a harness can fire session-start again after a compaction. The first
# snapshot of the session stays the baseline.
context.add(SetFlag(session, "baseline", git_snapshot, keep=True))

# `{paths}` becomes the changed Python files. With no changed file, the command
# does not run, and the stop is free.
changed_python = on_changed_paths(session, ["*.py"])
context.add(
    Limit(
        RequireCommand(
            [PYTHON, "-m", "ruff", "format", "--check", "{paths}"],
            reason="Run `ruff format` on these files.",
            on=STOPS,
            name="format",
            command_runner=changed_python,
        ),
        max_in_a_row=3,
    )
)
context.add(
    Limit(
        RequireCommand(
            [PYTHON, "-m", "ruff", "check", "{paths}"],
            on=STOPS,
            name="lint",
            command_runner=changed_python,
        ),
        max_in_a_row=3,
    )
)

context.add(
    Limit(RequireTests(on=STOPS), max_in_a_row=3),
    when=lambda event: changed_paths(event.root, session.get("baseline"), SOURCES),
)

aa.run(context)
