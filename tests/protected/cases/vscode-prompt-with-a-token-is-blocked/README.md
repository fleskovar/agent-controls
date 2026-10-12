# vscode-prompt-with-a-token-is-blocked

**Behaviour:** A prompt that carries an API token is blocked before the agent
sees it, and VS Code receives the block in its own output shape.

**Why this case exists:** Two things at once. It is the only case with a
**custom** process, written in the runner file as a project would write one, so
it doubles as the smallest working example. And `user-prompt` is the one hook
where VS Code does not follow the Claude Code shape: a block is
`continue: false` with `stopReason`, not `decision` with `reason`. An adapter
that copies the Claude Code branch here fails silently, and the token reaches
the model.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `BlockSecretsInPrompt` | A custom `PromptProcess` of about ten lines. |
| A prompt with `sk-ABCD1234EFGH5678` | A fake token that the expression matches. |
| Harness `vscode` | The harness with the different output shape. |

## Walkthrough

1. The hook is `user-prompt`, so the adapter fills `event.prompt` and leaves
   `event.tool` empty.
2. The process searches its expression in the prompt. `sk-` followed by twelve
   characters matches the first branch.
3. The process returns `block` with one reason that tells the user what to do
   instead. A block without a reason is refused by the framework, and here the
   reason is the whole value of the guard.
4. `Context.add` accepted the process, because `PromptProcess` declares allow and
   block, and VS Code delivers both on `user-prompt`.
5. VS Code has **no** context channel on this hook, so a reason is the only way
   to speak. The adapter renders `{"continue": false, "stopReason": ...}`.
6. The same runner file on Claude Code would produce
   `{"decision": "block", "reason": ...}`, and on Copilot CLI `Context.add` would
   refuse the process, because that harness cannot block a prompt at all.

## Baseline

Computed by hand from docs/requirements.md (R6, R12) and docs/data-model.md,
section 5.

## Run and debug

    make test-case CASE=vscode-prompt-with-a-token-is-blocked
    make debug-case CASE=vscode-prompt-with-a-token-is-blocked
