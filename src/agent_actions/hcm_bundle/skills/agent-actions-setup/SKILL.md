---
name: agent-actions-setup
description: Install Agent Actions in a project of any language, register its hooks in Claude Code, VS Code or GitHub Copilot CLI, and keep the installation up to date. Use when the user asks to add agent hooks or guardrails to a project, to register or remove the hooks, to upgrade agent_actions or its agent bundle, or when a hook does not run or fails.
---

# Install and manage Agent Actions in a project

Agent Actions is a Python package. It runs checks, named processes, on the
lifecycle hooks of an AI agent. The project can use any programming language.
Only the checks use Python.

## The parts

| Part | Location | Purpose |
| --- | --- | --- |
| The package | A Python virtual environment | Supplies `python -m agent_actions`. |
| The runner file | `.hooks/agent_checks.py` | Lists the processes of the project. One file for all harnesses. |
| The hook configuration | A file of the harness | Calls the runner file on each hook. `agent_actions install` writes it. |
| The session records | `.hooks/<timestamp>_<session>/` | State, input and output of each hook call. |

## The harness names

hcm and Agent Actions use different names for the same harness.

| Harness | `hcm -t` | `agent_actions --target` | Hook configuration file |
| --- | --- | --- | --- |
| Claude Code | `claude-code` | `claude` | `.claude/settings.json` |
| VS Code, GitHub Copilot agent | `copilot` | `vscode` | `.github/hooks/agent-actions-vscode.json` |
| GitHub Copilot CLI | `copilot-cli` | `copilot-cli` | `.github/hooks/agent-actions-copilot-cli.json` |

Install the hooks for one harness in each project. VS Code and Copilot CLI also
read `.claude/settings.json`, so a second harness runs the hooks two times.
The hooks and the limits of each harness are in [the harness page](./harnesses.md).

## Install in a new project

1. Make sure that Python 3.11 or later is available: `python --version`.
2. Create a virtual environment for the checks, and install the package into it.
   A Python project uses its own virtual environment.

   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install git+https://github.com/fleskovar/agent_actions
   ```

   On Linux and macOS, the interpreter is `.venv/bin/python`. Use this
   interpreter for each `python` command below.
3. Add these lines to `.gitignore`. The second line keeps the session records and
   the coverage reports out of git, and keeps the runner file in git.

   ```gitignore
   .venv/
   .hooks/*/
   ```
4. Write the runner file. Use the `agent-actions-guardrails` skill. It has a
   template for C#, Odin, Julia and Python, and a method for other languages.
5. Run each command of the runner file by hand in the project root. Fix the
   project until each command passes. A check that fails from the start blocks
   each stop of the agent.
6. Register the hooks. Give a timeout that is longer than the sum of the command
   timeouts on one hook. Each template gives its value at the top of the file.

   ```bash
   python -m agent_actions install .hooks/agent_checks.py --target claude --timeout 900
   ```

   The command prints the hooks that it registered. It keeps the other settings
   in the configuration file.
7. Run one hook by hand. Exit code 0 and no error text mean that the runner file loads.

   ```bash
   echo {} | python -m agent_actions run .hooks/agent_checks.py --harness claude --hook stop
   ```

   JSON on the standard output with `"decision": "block"` means that a check
   failed. That is a correct result when the project has a failing check.
8. Tell the user to start a new agent session. A harness reads its hook
   configuration when a session starts.
9. Commit the runner file and the files beside it. Do not rely on the hook
   configuration of a different machine: it contains the absolute path of the
   interpreter. On each machine, do steps 2 and 6 again after a clone.

For a first guardrail without the template, this runner file is sufficient:

```python
import agent_actions as aa
from agent_actions.processes import BlockWrites, LoopGuard, RequireCommand

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(LoopGuard(RequireCommand(["dotnet", "test", "--nologo"], name="tests")))
aa.run(context)
```

## Change the checks

1. Change the runner file. Use the `agent-actions-guardrails` skill for the included
   processes, and the `agent-actions-processes` skill for a new process class.
2. Register the hooks again with the same `install` command. The command derives
   the hooks from the processes. A new process can need a hook that is not
   registered.
3. Run one hook by hand, as in step 7 above.

If a guardrail protects the runner file, do not work around it. Ask the user to
make the change, or to remove the pattern.

## Upgrade

1. Upgrade the package in the virtual environment of the project:
   `python -m pip install --upgrade git+https://github.com/fleskovar/agent_actions`.
2. Update the skills of this bundle. The command registers the bundle of the new
   package version in hcm, then runs `hcm update agent-actions` in the project.

   ```bash
   python -m agent_actions hcm update -t claude-code --no-prompt
   ```
3. Register the hooks again, as in step 6 above.
4. Compare the runner file with the new template of its language in the
   `agent-actions-guardrails` skill. Tell the user about the differences. Do not
   replace the settings of the project.

`python -m agent_actions hcm init` only registers the bundle. Use it on a machine
that does not have the bundle. Then install the bundle into a project with
`hcm install agent-actions -t <hcm target>`.

## Remove the hooks

Agent Actions has no uninstall command. Open the hook configuration file of the
harness. Delete each hook entry whose command contains the path of the runner
file. Keep the other entries.

## When a hook fails

Read [the troubleshooting page](./troubleshooting.md). It shows how to read a
session record, how to replay one hook call, and the common errors.
