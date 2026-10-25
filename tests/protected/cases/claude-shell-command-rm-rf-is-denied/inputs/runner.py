import agent_controls as aa
from agent_controls.processes import BlockShellCommands

context = aa.get_current_context()
context.add(
    BlockShellCommands(
        [
            r"\brm\s+-rf\b",
            r"git\s+push\s+.*--force",
            r"\bcurl\b.*\|\s*(ba)?sh",
        ]
    )
)
aa.run(context)
