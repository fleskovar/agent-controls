# claude-shell-command-reading-a-secret-is-denied

**Behaviour:** `BlockReads` also blocks a shell command that mentions a protected
path, because a shell reads files without a read tool.

**Why this case exists:** `cat .env` is the simplest way around a guard that only
inspects read tools. The check is a substring heuristic, and this case states its
shape so that a later change does not weaken it by accident.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `cat .env | grep TOKEN` | A shell command that names a protected file. |
| Pattern `.env` | The literal part of the pattern is the whole pattern. |
| Pattern `secrets/**` | Not mentioned in the command, so it does not match. |

## Walkthrough

1. `Bash` gives a tool of kind `shell`, with the command text.
2. `BlockReads` guards read, search and write tools. The kind is `shell`, so the
   path check does not apply. `check_shell` is true by default for this guard, so
   the command check runs.
3. The command is lowercased and its backslashes become `/`:
   `cat .env | grep token`.
4. For each pattern the guard takes the longest part without a wildcard. For
   `.env` that is `.env`; for `secrets/**` it is `secrets`.
5. `.env` occurs in the command text, so the first pattern matches and the search
   stops.
6. The verdict is `block`. The reason names the pattern, not a path, because the
   command mentions no resolvable path.

A command that builds the name at run time, for example
`cat .e"n"v`, is not detected. The heuristic and its limit are recorded in the
source and in docs/processes.md.

## Baseline

Computed by hand from docs/requirements.md (R36, R37).

## Run and debug

    make test-case CASE=claude-shell-command-reading-a-secret-is-denied
    make debug-case CASE=claude-shell-command-reading-a-secret-is-denied
