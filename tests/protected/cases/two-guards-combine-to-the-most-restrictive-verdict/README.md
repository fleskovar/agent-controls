# two-guards-combine-to-the-most-restrictive-verdict

**Behaviour:** When two processes run on one hook, the most restrictive verdict
wins, and only the reasons of the winning verdict reach the agent. Both processes
still run, and both record their state.

**Why this case exists:** A real project runs five or six guardrails on
`pre-tool`. This case pins the three rules that decide what the agent sees: the
order of severity, the filtering of reasons, and the fact that an allow is not
silent in the record even though it is silent to the agent.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `ToolCallBudget(5)` added first | A stateful process that allows, and counts the call. |
| `BlockWrites(["tests/**"])` added second | A process that blocks the same call. |
| A write to `tests/test_pricing.py` | One call that both processes see. |

## Walkthrough

1. Processes run in the order they were added. `ToolCallBudget` runs first.
2. The budget counts every tool kind. The recorded state is empty, so the counter
   starts at 0, which is below 5. The counter becomes 1 and the verdict is
   `allow`, with the reason `1 of 5 tool calls used.`
3. `BlockWrites` runs next. The path matches `tests/**`, so the verdict is
   `block`.
4. The combination compares the verdicts: block beats ask beats allow. The
   combined verdict is `block`.
5. Only the reasons of processes that returned the **winning** verdict are kept,
   so the agent reads the guard reason and not `1 of 5 tool calls used.` Reasons
   of an allow go to log.txt, which keeps one line per tool call out of the agent
   context.
6. state.json holds both processes: the counter of the budget, now 1, and the
   block of the guard. The budget counted a call that never ran, which is the
   deliberate choice: the agent asked for it.

## Baseline

Computed by hand from docs/requirements.md (R13, R19, R43).

## Run and debug

    make test-case CASE=two-guards-combine-to-the-most-restrictive-verdict
    make debug-case CASE=two-guards-combine-to-the-most-restrictive-verdict
