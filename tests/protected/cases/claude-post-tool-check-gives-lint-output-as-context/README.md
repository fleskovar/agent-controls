# claude-post-tool-check-gives-lint-output-as-context

**Behaviour:** After a write, the linter runs on the edited file. It fails, and
its output reaches the agent as context, not as a block.

**Why this case exists:** Feedback after an edit is worth more than feedback at
the end of the turn, because the agent still has the file in mind. The case also
pins the deliberate choice of `CheckAfterEdit`: it never blocks, so the same
process works on every harness, including the one that cannot block a post-tool
call.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `failing_ruff` | An injected command runner: exit code 1 and one finding. |
| `"ruff check {paths}"` | A command with the placeholder for the edited paths. |
| `patterns=["*.py"]` | The check runs for Python files only. |
| A `Write` of `src/pricing.py` | A write tool, so the check applies. |

## Walkthrough

1. The hook is `post-tool`, and the tool kind is `write`, so the check applies.
2. The edited path is `{{root}}/src/pricing.py`. Relative to the root it is
   `src/pricing.py`, which matches `*.py`, so the file is checked.
3. `{paths}` becomes the edited path. The path needs no shell quoting, so the
   command is `ruff check {{root}}/src/pricing.py`.
4. The runner answers exit code 1 with one finding.
5. The verdict stays `allow`, and the failure goes into the **context** of the
   result: the command, the exit code, the reason and the output.
6. Claude Code accepts context on `post-tool` as
   `hookSpecificOutput.additionalContext`, so the agent reads the lint finding
   with its next message.

The companion case `copilot-cli-post-tool-check-uses-additional-context` runs the
same runner file on another harness.

## Baseline

Computed by hand from docs/requirements.md (R41) and docs/data-model.md, section 5.

## Run and debug

    make test-case CASE=claude-post-tool-check-gives-lint-output-as-context
    make debug-case CASE=claude-post-tool-check-gives-lint-output-as-context
