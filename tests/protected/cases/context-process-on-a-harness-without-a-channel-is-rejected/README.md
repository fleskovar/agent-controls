# context-process-on-a-harness-without-a-channel-is-rejected

**Behaviour:** A process that adds context is refused when the target harness has
no context channel on that hook. The refusal happens while the runner file builds
its context, and the run exits with code 1.

**Why this case exists:** This is the add-time half of the silent-failure
protection. The companion case `stop-process-that-asks-fails-loudly` covers the
run-time half. Here the mistake is a portability mistake: the runner file is
correct for Claude Code and for VS Code, and wrong for Copilot CLI. Without the
check, the process would run on every session start, return text, and the text
would go nowhere.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `AddContext(...)` | A process that declares `uses_context`. |
| Harness `copilot-cli` | The harness whose `sessionStart` has no context channel. |
| Hook `session-start` | A hook the harness does have, so the hook itself is not the problem. |

## Walkthrough

1. The runner file calls `context.add(AddContext(...))`.
2. `Context.add` reads the capability of `session-start` for `copilot-cli`: the
   verdicts are allow only, and the context channel is absent.
3. The declared verdicts of the process fit, because it only allows. The context
   does not fit, so the check collects one problem.
4. `Context.add` raises, and the message names the process, the harness, the hook
   and the reason, so the author can fix the runner file without reading the
   framework source.
5. The error is caught where the runner file is loaded, so the CLI writes the
   message to stderr and exits with code 1. The agent receives no decision.
6. No process ran, so state.json holds no step for this call. The raw payload and
   the error are in io.json.

The same error appears during `agent_actions install`, which is where the author
meets it first, before any agent runs.

## Baseline

Computed by hand from docs/requirements.md (R8, R15) and the capability table in
docs/data-model.md, section 3.

## Run and debug

    make test-case CASE=context-process-on-a-harness-without-a-channel-is-rejected
    make debug-case CASE=context-process-on-a-harness-without-a-channel-is-rejected
