# copilot-cli-read-of-env-file-is-denied

**Behaviour:** In Copilot CLI, `BlockReads` denies a `view` of `.env`, and the
decision is a top-level field, not `hookSpecificOutput`.

**Why this case exists:** Copilot CLI differs from the other two harnesses in
three ways at the same time: camelCase fields, `toolArgs` as a JSON **string**,
and another output shape. The same runner file must still work unchanged.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `sessionId`, `toolName` | The camelCase payload of Copilot CLI. |
| `toolArgs` as a string | The adapter decodes the JSON string before it looks for paths. |
| `"path": ".env"` | A relative path, and the `path` argument name of Copilot CLI. |
| Pattern `.env` | An exact match, not a glob. |

## Walkthrough

1. The adapter reads `toolName` `view`. `view` is the Copilot CLI read tool, so
   the kind is `read`.
2. `toolArgs` is a string. The adapter decodes it to `{"path": ".env"}`. `path`
   is a Copilot CLI path key, so the path is `.env`.
3. `BlockReads` guards read, search and write tools. The kind is `read`, so it
   checks the path.
4. The path is relative, so it resolves against `cwd`, which is the project root.
   Relative to the root it stays `.env`.
5. Pattern `.env` is equal to the path, so it matches. `secrets/**` is not
   compared.
6. The result is `block` with one reason, prefixed with `[BlockReads]`.
7. Copilot CLI takes a `preToolUse` block as the top-level fields
   `permissionDecision` and `permissionDecisionReason`.
8. The session id gives the short id `b7e2c4d1`, so the agent folder is
   `20260915T100000000_b7e2c4d1/main-agent`.

## Baseline

Computed by hand from docs/requirements.md (R36) and from the GitHub Copilot CLI
hooks reference (input schema and preToolUse output).

## Run and debug

    make test-case CASE=copilot-cli-read-of-env-file-is-denied
    make debug-case CASE=copilot-cli-read-of-env-file-is-denied
