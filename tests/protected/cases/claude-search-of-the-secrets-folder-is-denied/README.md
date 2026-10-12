# claude-search-of-the-secrets-folder-is-denied

**Behaviour:** A search of a protected folder is denied, and the pattern
`secrets/**` covers the folder `secrets` itself, not only the files inside it.

**Why this case exists:** A search returns file content, so it reads secrets as
surely as a read tool does. This case also pins a pattern rule that surprised the
author: before the rule existed, `secrets/**` matched `secrets/prod.json` but not
`secrets`, so a search of the whole folder went through.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `tool_name: "Grep"` | A search tool, which `BlockReads` guards as well. |
| `path: "secrets"` | The folder itself, with no file name. |
| Pattern `secrets/**` | Must cover the folder, not only its content. |

## Walkthrough

1. `Grep` is in the Claude Code search tools, so the kind is `search`.
2. `path` is a Claude Code path key, so the path is `secrets`. It is relative, so
   it resolves against `cwd`, which is the project root, and stays `secrets`.
3. `BlockReads` guards read, search and write tools, so it checks the path.
4. Pattern `.env` does not match.
5. Pattern `secrets/**`: the trailing `/**` is removed for the folder comparison,
   so the pattern covers the folder `secrets` and everything under it. The path
   is equal to `secrets`, so it matches.
6. The verdict is `block`.

A search that names **no** path is not blocked. A repository-wide search can
still reach a secret file that no ignore file excludes; docs/processes.md records
that limit.

## Baseline

Computed by hand from docs/requirements.md (R36) and the pattern rules in
docs/processes.md.

## Run and debug

    make test-case CASE=claude-search-of-the-secrets-folder-is-denied
    make debug-case CASE=claude-search-of-the-secrets-folder-is-denied
