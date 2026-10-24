"""Exit strategies: checks that hold the agent a limited number of times.

- Stop: the tests must pass. After 5 failed stops in a row, or 10 in the session,
  the agent can stop. The last block tells it to try a different approach, or to
  ask the user for help. The release sets the project flag `needs-review`.
  The count in a row is for one problem: a new prompt, or a different failure,
  starts it again. The total does not start again.
- Start of a later session: while `needs-review` is set, the agent gets a note.
  A pass of the tests deletes the flag.
- Before a write to `migrations/`: the write is denied. After 2 denied writes in a
  row, the next write asks the user. The agent can have a good reason, and a
  person decides.

The counts are per agent. Each subagent has its own counts.

Copilot CLI has no context channel on session-start. Remove the note there.
"""

import agent_actions as aa
from agent_actions.processes import (
    AddContext,
    BlockWrites,
    Limit,
    RequireTests,
    clear_on_pass,
    problem_text,
)

NOTE = (
    "An earlier session stopped before the tests passed, and the user must review it. "
    "Ask the user about the review before you start other work."
)

context = aa.get_current_context()
flags = context.flags

context.add(
    Limit(
        RequireTests(command_runner=clear_on_pass(flags, "needs-review")),
        max_in_a_row=5,
        max_total=10,
        reset_on=[aa.Hook.USER_PROMPT],
        problem=problem_text,
        flags=flags,
        flag="needs-review",
    )
)
context.add(AddContext(NOTE, name="review-note"), when=lambda _: flags.get("needs-review"))
context.add(
    Limit(
        BlockWrites(["migrations/**"], reason="Only a person changes the migrations."),
        max_in_a_row=2,
        then=aa.Verdict.ASK,
    )
)

aa.run(context)
