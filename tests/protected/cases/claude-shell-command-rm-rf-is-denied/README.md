# claude-shell-command-rm-rf-is-denied

**Behaviour:** A shell command that matches a blocked expression is denied, and
the reason names the expression that matched.

**Why this case exists:** Path guards see tool arguments, not shell commands. A
recursive delete, a force push or a piped installer reaches the same files
without any write tool. This guard is the shell half of the protection.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `rm -rf build dist` | A command that matches the first expression. |
| Three expressions | The reason must name the one that matched, not the list. |
| `tool_name: "Bash"` | A Claude Code shell tool, so the tool kind is `shell`. |

## Walkthrough

1. `Bash` is in the Claude Code shell tools, so the kind is `shell` and the
   adapter copies `tool_input.command` into the tool call.
2. `BlockShellCommands` searches each expression in order, case-insensitively.
3. The first expression `\brm\s+-rf\b` matches `rm -rf build dist`: `\b` sits
   at the start of `rm`, `\s+` matches the space, and `\b` sits after `-rf`.
4. The search stops at the first match, and the reason quotes that expression, so
   a reader of the transcript can find the rule that fired.
5. The verdict is `block`, which Claude Code takes as `permissionDecision:
   "deny"`.

## Baseline

Computed by hand from docs/requirements.md (R38) and docs/processes.md
(BlockShellCommands).

## Run and debug

    make test-case CASE=claude-shell-command-rm-rf-is-denied
    make debug-case CASE=claude-shell-command-rm-rf-is-denied
