# install-claude-keeps-existing-settings

**Behaviour:** `agent_actions install` adds one hook entry per hook that the
runner file uses, and leaves every other setting of the file unchanged.

**Why this case exists:** The settings file belongs to the user. An install that
drops a permission list or a formatter hook destroys work that the framework
never owned. The case also pins which hooks the install derives from the runner
file, and which entries get a tool matcher.

## Inputs

| Row | Demonstrates |
| --- | --- |
| `permissions.allow` | A setting that the framework does not know and must keep. |
| `PostToolUse` prettier entry | A foreign hook entry, on a hook the runner file does not use. |
| `BlockWrites` | A pre-tool process. |
| `LoopGuard(RequireTests())` | A stop process; the guard takes the hooks of the process it wraps. |
| `"command": "install"` in case.json | The case runs install, not a hook call. |

## Walkthrough

1. Install loads the runner file with no hook and no payload, so the file only
   builds its context.
2. The context reports the hooks that its processes use, in lifecycle order:
   `pre-tool` from `BlockWrites`, and `stop` from the loop guard, which takes its
   hooks from `RequireTests`.
3. For each hook, install builds the command `python -m agent_actions run
   runner.py --harness claude --hook <hook>`. The case runner passes `python` as
   the interpreter. A real install passes the absolute path of the interpreter
   that runs it, which is the virtual environment of the project.
4. No argument has a character that needs quoting, so the command stays
   unquoted, which works in bash, cmd and PowerShell.
5. Install reads the existing settings, and removes only entries of the same
   runner file. There are none, so nothing is removed.
6. `PreToolUse` is a tool event, so its entry gets `"matcher": "*"`. `Stop` is
   not, so its entry has no matcher.
7. `permissions` and the prettier entry are copied unchanged.
8. A second install with the same runner file gives the same file: the entries
   of this runner file are removed first, then written again.

## Baseline

Computed by hand from docs/requirements.md (R31) and the Claude Code settings
format (hooks, matcher, timeout).

## Run and debug

    make test-case CASE=install-claude-keeps-existing-settings
    make debug-case CASE=install-claude-keeps-existing-settings
