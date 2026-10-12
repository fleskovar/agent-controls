# claude-stop-is-blocked-while-tests-fail

**Behaviour:** When the agent wants to stop and the test command fails, the stop
is blocked, and the agent receives the failure and the test output.

**Why this case exists:** This guardrail keeps an agent honest about the word
"done". The case also pins two format rules: several reasons join with a
newline, and each reason carries its process name, so an agent with five
guardrails knows which one spoke.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `failing_pytest` | An injected command runner: exit code 1 and fixed output. No subprocess, so the case is deterministic. |
| Command `["pytest", "-q"]` | A sequence command, shown to the agent as `pytest -q`. |
| `stop_hook_active: false` | The first stop of this turn. |

## Walkthrough

1. `RequireTests` runs on the `stop` hook. It calls the command runner with the
   project root as the working folder.
2. The runner answers exit code 1 and the output `1 failed, 4 passed`.
3. The exit code is not 0, so the result is `block` with two reasons: the failure
   line with the reason of `RequireTests`, and the output. The output is shorter
   than 3000 characters, so the tail is the whole output.
4. The combination prefixes both reasons with `[RequireTests]` and joins them
   with a newline.
5. Claude Code takes a `Stop` block as `{"decision": "block", "reason": ...}`.
   The agent continues to work and reads the reason.
6. The exit code of the CLI is 0. A blocked stop is a normal answer, not an error.
7. `RequireTests` declares no state. The retry counter belongs to `LoopGuard`,
   which the next case shows.

## Baseline

Computed by hand from docs/requirements.md (R13, R39) and from the Claude Code
hooks reference (Stop decision control).

## Run and debug

    make test-case CASE=claude-stop-is-blocked-while-tests-fail
    make debug-case CASE=claude-stop-is-blocked-while-tests-fail
