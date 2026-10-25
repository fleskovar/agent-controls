"""No change of the source code before the agent reads the architecture guide.

- After a read tool opens `docs/architecture.md`: set the session flag `guide-read`.
- Before a write tool changes `src/`: block it while the flag is not set. The
  reason tells the agent which file to read.

One read opens the gate for the full session. The session flags are for the main
agent and its subagents, so a read by a subagent also counts.

Change GUIDE and GUARDED to use the idea for other rules, for example "read the
migration guide before you change `migrations/`".
"""

import agent_controls as aa
from agent_controls.processes import BlockWrites, SetFlag
from agent_controls.processes.paths import matching_pattern, relative_path

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
