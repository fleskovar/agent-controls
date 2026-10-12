"""Flags that a person sets: switches for the guardrails, and a note for each session.

The framework reads `.hooks/flags.json` at each hook call. Thus a person can edit
that file to change the behaviour of the agents. The next hook call uses the new
value, in each open session, and `agent_actions install` is not necessary.

    {
      "freeze": "Release 2.4 is in review until Friday.",
      "note": "Do not use the billing sandbox this week. Its data is wrong."
    }

- `freeze`: while it has a value, write tools cannot change `src/`. The agent
  reads the value as the reason.
- `note`: each session starts with this text in the context of the agent.

Delete a flag from the file to switch it off.

A flag is a file, so an agent can also change it. The first process below blocks
the write tools on `.hooks/`, and each shell command that mentions `.hooks`.

Copilot CLI has no context channel on session-start. Remove the note there.
"""

import agent_actions as aa
from agent_actions.processes import AddContext, BlockWrites

context = aa.get_current_context()
flags = context.flags

context.add(BlockWrites([".hooks/**"], check_shell=True, name="protect-flags"))

# The runner file runs at each hook call, after the framework loads the flags.
# Thus the text of a flag can be a part of a reason or of a context.
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
