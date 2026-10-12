# stop-process-that-asks-fails-loudly

**Behaviour:** A stop process that returns `ask` stops the run with exit code 1
and a message on stderr. The agent never receives a decision that the harness
cannot deliver.

**Why this case exists:** This is the failure mode that the framework exists to
remove. A `Stop` hook has no channel for "ask the user". A harness ignores such
output without an error, so the guardrail looks alive and protects nothing. The
run must fail instead, in a way a person can see.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `AskBeforeStopping` | A `StopProcess`, so `context.add` accepts it: its declared verdicts are allow and block. |
| `return aa.ask(...)` | The process returns a verdict it did not declare. |
| Harness `claude`, hook `stop` | The hook whose capability holds allow and block only. |

## Walkthrough

1. `context.add` checks the process against the harness. `StopProcess` declares
   the verdicts allow and block, and Claude Code delivers both on `stop`, so the
   process is accepted. The add-time check cannot see what `run` returns.
2. The engine runs the process. It returns `ask`.
3. The run-time check compares the verdict with the deliverable set, which is the
   intersection of the declared verdicts and the capability of the hook: allow
   and block. `ask` is not in it.
4. The check raises. The error names the process, the verdict, the hook, the
   harness and the verdicts that can reach the agent.
5. The CLI writes the message to stderr and exits with code 1. Every supported
   harness shows a non-blocking hook error to the user.
6. No process record is written, so state.json holds no step for this call. The
   raw call and the error are still in io.json, which is how the author debugs
   the runner file.

## Baseline

Computed by hand from docs/requirements.md (R15) and task.md, which names this
silent failure as the behaviour to prevent.

## Run and debug

    make test-case CASE=stop-process-that-asks-fails-loudly
    make debug-case CASE=stop-process-that-asks-fails-loudly
