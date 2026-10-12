# copilot-cli-post-tool-check-uses-additional-context

**Behaviour:** The runner file of the Claude Code post-tool case works unchanged
on Copilot CLI. Only the shape of the answer differs.

**Why this case exists:** "One runner file for every harness" is the main claim
of the framework. The pair of cases proves it for a process, rather than stating
it in a document: the same `inputs/runner.py` text, two harnesses, two output
shapes, one behaviour.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `inputs/runner.py` | The same file as in the Claude Code case. |
| `toolName: "edit"` | The Copilot CLI write tool. |
| `toolArgs.path` | The Copilot CLI path key, as an object this time, not a string. |
| `toolResult.textResultForLlm` | The Copilot CLI shape for the tool output. |

## Walkthrough

1. `edit` is in the Copilot CLI write tools, so the kind is `write`, exactly as
   `Write` in Claude Code.
2. `toolArgs` arrives as an object here, so no decoding is needed. `path` is a
   path key, so the edited path is `{{root}}/src/pricing.py`.
3. The check runs and fails, as in the Claude Code case, and the result is an
   `allow` that carries context.
4. Copilot CLI has a context channel on `postToolUse`, and it reads it as a
   **top-level** `additionalContext` field, not inside `hookSpecificOutput`.
5. The process code never mentions a harness. The adapter alone decides the shape.

## Baseline

Computed by hand from docs/requirements.md (R41) and docs/data-model.md,
section 5.

## Run and debug

    make test-case CASE=copilot-cli-post-tool-check-uses-additional-context
    make debug-case CASE=copilot-cli-post-tool-check-uses-additional-context
