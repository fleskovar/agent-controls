"""A flag that outlives the session: "the tests are due".

- After a write tool changes a source file: set the project flag `tests-due`.
- Stop: while the flag is set, the tests must pass. A pass deletes the flag.
- After 3 blocked stops, LoopGuard lets the agent stop. The flag stays.
- Start of a later session: the flag is still there. The agent gets a note, and
  it cannot stop until the tests pass, also when it changes no file.

The flag is in `.hooks/flags.json`. A session that the user closes while the tests
fail leaves the same flag, so the next session gets the debt.

The condition reads the tool call, not git. It is fast, but it does not see a
change that a shell command made. `checks_on_changed_files.py` shows the git form.

Copilot CLI has no context channel on session-start. Remove the note there.
"""

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
