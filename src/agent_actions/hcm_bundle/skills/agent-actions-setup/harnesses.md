# What each harness can do

A runner file uses neutral hook names. Agent Actions translates them for each
harness. `context.add` rejects a process that cannot work in the target harness,
and the error names the reason.

## Hooks

| Neutral hook | When it runs | Claude Code | VS Code | Copilot CLI |
| --- | --- | --- | --- | --- |
| `session-start` | A session starts. | yes | yes | yes |
| `user-prompt` | The user sends a prompt. | yes | yes | yes |
| `pre-tool` | Before a tool call. | yes | yes | yes |
| `post-tool` | After a tool call. | yes | yes | yes |
| `stop` | The agent wants to finish. | yes | yes | yes |
| `subagent-start` | A subagent starts. | yes | yes | no |
| `subagent-stop` | A subagent wants to finish. | yes | yes | yes |
| `pre-compact` | Before the harness compacts the context. | yes | yes | no |
| `session-end` | A session ends. | yes | no | yes |

## What reaches the agent

A verdict is the decision of a process: `allow`, `ask` or `block`. Context is
text that a process adds for the agent.

| Hook | Claude Code | VS Code | Copilot CLI |
| --- | --- | --- | --- |
| `session-start` | allow, context | allow, context | allow |
| `user-prompt` | allow, block, context | allow, block | allow |
| `pre-tool` | allow, ask, block, context | allow, ask, block, context | allow, ask, block |
| `post-tool` | allow, block, context | allow, block, context | allow, context |
| `stop` | allow, block | allow, block | allow, block |
| `subagent-start` | allow, context | allow, context | not available |
| `subagent-stop` | allow, block | allow, block | allow, block |
| `pre-compact` | allow | allow | not available |
| `session-end` | allow | not available | allow |

## Consequences

- `stop` and `subagent-stop` have no context channel. To tell the agent something
  there, block the stop and put the text in the reason.
- An `allow` on `pre-tool` gives no decision to the harness. The permission rules
  of the harness still apply.
- Copilot CLI has no context on `session-start`. `RunCommand`, `AddContext` and
  `RevertWrites` cannot use that hook there. Use `post-tool`.
- Copilot CLI cannot block a prompt. A `PromptProcess` is rejected there.
- VS Code has no context on `user-prompt`.
- The runner templates of the `agent-actions-guardrails` skill read these
  capabilities. Thus one template works in the three harnesses.

## Known limits

- Install the hooks for one harness in each project. VS Code reads
  `.claude/settings.json` and `.github/hooks/*.json`. Copilot CLI reads
  `.claude/settings.json`. With two installations, one harness runs the hooks of
  the other harness too.
- The tool names of each harness come from its documentation on 2026-09-15. A new
  tool of a harness has the kind `other` until the adapter knows it. A path guard
  does not see the paths of such a tool.
- Agent Actions generates `command` hooks only. It does not change the input of
  a tool call.
