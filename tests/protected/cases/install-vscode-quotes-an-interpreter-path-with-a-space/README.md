# install-vscode-quotes-an-interpreter-path-with-a-space

**Behaviour:** `install` writes one entry per hook for VS Code, with a POSIX
command and a PowerShell command, and it quotes an interpreter path that contains
a space.

**Why this case exists:** The default virtual environment path on Windows often
sits under a folder with a space. An unquoted path makes the harness run
`C:/Program`, and the hook fails on every call with an error that looks like a
framework bug. The two commands also differ per shell, and this case is the only
place where that difference is visible in data.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `"python": "C:/Program Files/py.exe"` | An interpreter path with a space. |
| `BlockWrites` and `CheckAfterEdit` | Two processes on two different hooks. |
| `"timeout": 120` | A timeout that is not the default. |

## Walkthrough

1. Install loads the runner file with no hook and no payload, and asks the
   context which hooks its processes use: `pre-tool` and `post-tool`, in
   lifecycle order.
2. For each hook, the argument list is the interpreter, `-m agent_actions run`,
   the runner file, `--harness vscode` and `--hook <hook>`.
3. The interpreter path contains a space, so the unquoted form is not safe. The
   POSIX form quotes that one argument and leaves the rest bare.
4. The PowerShell form quotes **every** argument and puts the call operator `&`
   in front, because a quoted string at the start of a PowerShell line is a
   string, not a command.
5. VS Code takes the POSIX form as `command` and the PowerShell form as
   `windows`, and uses the second one on Windows.
6. The file did not exist, so the result holds the two entries and nothing else.
   The Claude Code case `install-claude-keeps-existing-settings` covers the merge
   into a file that already has content.

## Baseline

Computed by hand from docs/requirements.md (R31) and docs/data-model.md,
section 7.

## Run and debug

    make test-case CASE=install-vscode-quotes-an-interpreter-path-with-a-space
    make debug-case CASE=install-vscode-quotes-an-interpreter-path-with-a-space
