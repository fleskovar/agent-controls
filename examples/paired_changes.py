"""Files that must change together.

- Session start: save the state of the git work tree as the baseline.
- Stop: when a file of one group changed after the baseline, a file of its paired
  group must also show a change. If not, the stop is blocked.

The two pairs below:

- A change of the public API needs a change of the documentation.
- A change of the dependencies needs an entry in the changelog.

Limit lets the agent stop after 3 blocked stops, for the change that needs no
paired change. The agent then reports that to the user.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import agent_actions as aa
from agent_actions.processes import Limit, SetFlag, changed_paths, git_snapshot


class RequirePairedChange(aa.StopProcess):
    """Blocks the stop when `changed` files changed after the baseline and no `paired` file did."""

    def __init__(
        self,
        flags: Mapping[str, Any],
        changed: Sequence[str],
        paired: Sequence[str],
        reason: str,
        *,
        name: str,
    ) -> None:
        self.flags = flags
        self.changed = changed
        self.paired = paired
        self.reason = reason
        self.name = name

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        baseline = self.flags.get("baseline")
        trigger = changed_paths(event.root, baseline, self.changed)
        if not trigger or changed_paths(event.root, baseline, self.paired):
            return aa.allow()
        return aa.block(
            f"You changed {', '.join(trigger)}, but no file in {', '.join(self.paired)}. "
            f"{self.reason}"
        )


context = aa.get_current_context()
session = context.session_flags

context.add(SetFlag(session, "baseline", git_snapshot, keep=True))

context.add(
    Limit(
        RequirePairedChange(
            session,
            ["src/api/**"],
            ["docs/**"],
            "Update the documentation of the API.",
            name="api-needs-docs",
        ),
        max_in_a_row=3,
    )
)
context.add(
    Limit(
        RequirePairedChange(
            session,
            ["pyproject.toml", "requirements*.txt"],
            ["CHANGELOG.md"],
            "Add the dependency change to the changelog.",
            name="dependencies-need-changelog",
        ),
        max_in_a_row=3,
    )
)

aa.run(context)
