# tool-call-budget-blocks-after-the-recorded-limit

**Behaviour:** The tool call budget counts across hook calls. When the recorded
counter has reached the maximum, the next call is blocked, and the counter does
not grow further.

**Why this case exists:** Every hook call is a new operating system process, so a
counter only exists if the framework restores it. This case proves the restore
path with a recorded state that a previous run wrote, and it pins the rule that a
blocked call is not counted, so the number in the reason stays true.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/project/.hooks/.../state.json` | A recorded step with `calls: 3`. |
| `ToolCallBudget(3)` | A maximum that the recorded counter has reached. |
| A `Read` call | Any tool kind counts, not only writes. |

## Walkthrough

1. The short id of the session is `7e8f9a0b`, and the seeded folder holds a
   session.json with the same full id, so the framework reuses the folder. The
   folder list shows no new folder.
2. `latest_states` takes the newest timestamp in state.json and returns
   `{"calls": 3}` for `ToolCallBudget`.
3. The process restores its state. `__state__` sets `calls` to 0, and the
   recorded value 3 replaces it.
4. The tool kind is `read`, which is in the counted kinds, so the call counts.
5. `calls` is 3 and the maximum is 3, so the condition `calls >= max_calls`
   holds. The verdict is `block`, and the reason states the budget.
6. The counter is **not** raised, so the recorded state stays at 3. A blocked
   call never ran, so counting it would make every later reason wrong.

## Baseline

Computed by hand from docs/requirements.md (R18, R43).

## Run and debug

    make test-case CASE=tool-call-budget-blocks-after-the-recorded-limit
    make debug-case CASE=tool-call-budget-blocks-after-the-recorded-limit
