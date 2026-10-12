# claude-command-reads-the-hook-event-on-stdin

**Behaviour:** A command process writes the hook event as JSON to the standard input of
its command. The command reads the edited file from it and answers on its output.

**Why this case exists:** This is the contract for a program in another language: read
one JSON object from stdin, print the message for the agent, exit with 0 or 1.
The JSON has the neutral names of the framework, not the names of the harness,
so one program works for every harness.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `failing_dotnet_test` | The stand-in command. It builds its first output line from stdin only. |
| `hook_event_name: "PostToolUse"` | The Claude Code name. The command must see `post-tool`. |
| `tool_name: "Write"` | A Claude Code write tool. The command must see the kind `write`. |
| `tool_input.file_path` | A Claude Code path key. The command must see it in `tool.paths`. |
| `patterns=["*.cs"]` | The edited file is a C# file, so the command runs. |

## Walkthrough

1. `Write` is a Claude Code write tool and `file_path` is a path key, so the
   neutral event has `tool.name: "Write"`, `tool.kind: "write"` and
   `tool.paths: ["{{root}}/src/Pricing.cs"]`.
2. `src/Pricing.cs` matches `*.cs`, so `CheckAfterEdit` runs its command.
3. The text for stdin is `event.to_record()` as JSON: the fields of
   `HookInput` without `raw`. Its first two keys are `harness: "claude"` and
   `hook: "post-tool"`.
4. The stand-in command reads four values from stdin and prints
   `claude post-tool: Write (write) on {{root}}/src/Pricing.cs`. Each value is
   a neutral name. `PostToolUse` does not occur.
5. The command exits with 1, so `CheckAfterEdit` gives its output to the
   agent as context, after the sentence with the command and the exit code.
6. The same contract holds for `RequireCommand` and `RunCommand`. They call
   the same command runner with the same text.

## Baseline

Computed by hand from docs/requirements.md (R46), docs/data-model.md and the
section "Commands in other languages" in docs/processes.md.

## Run and debug

    make test-case CASE=claude-command-reads-the-hook-event-on-stdin
    make debug-case CASE=claude-command-reads-the-hook-event-on-stdin
