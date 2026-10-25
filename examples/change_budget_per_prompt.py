"""A limit on the number of files that one prompt changes.

- Each user prompt: save the state of the git work tree in the session flag `turn`.
  This snapshot is replaced at each prompt, so it is the baseline of one turn.
- Before a write tool: count the files that changed after that snapshot. At
  MAX_FILES or more, the harness asks the user to approve the write.

A small request that grows into a change of many files stops at the user, who
decides. The next prompt starts a new count.

The count reads git. Thus the files that a shell command or a subagent changed
are in it. Without a snapshot, each uncommitted change is in the count.
"""

from collections.abc import Mapping
from typing import Any

import agent_controls as aa
from agent_controls.processes import SetFlag, changed_paths, git_snapshot

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

# The condition keeps git out of each read and each search.
context.add(
    ChangeBudget(session, MAX_FILES),
    when=lambda event: event.tool is not None and event.tool.kind is aa.ToolKind.WRITE,
)

aa.run(context)
