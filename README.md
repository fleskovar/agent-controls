# Agent Controls

Agent Controls is a Python SDK and CLI for AI agent lifecycle hooks. You write
guardrails and checks as Python classes. The framework runs them on the hooks of
Claude Code, VS Code (GitHub Copilot agent) and GitHub Copilot CLI, keeps their
state between calls, and records each call under `.hooks/`.

- One runner file works in all supported harnesses.
- A process on a hook that cannot deliver its result fails loudly, not silently.
- Each process can declare state. The framework restores and records it.
- Flags keep state between processes and between sessions. A `when` condition
  starts a process only when a flag, or a change in the work tree, asks for it.
- Included processes: path guards, shell guard, required tests and commands,
  coverage gate, limits with exit strategies, post-edit check, revert of
  protected files, context injection, tool call budget, flags and git snapshots.
- One runtime dependency: GitPython. Python 3.11 or later.

## Quick start

1. Install the package in the virtual environment of your project:

   ```bash
   pip install git+https://github.com/fleskovar/agent-controls
   ```

2. Create a runner file, for example `agent_checks.py`:

   ```python
   import agent_controls as aa
   from agent_controls.processes import BlockReads, BlockWrites, Limit, RequireTests

   context = aa.get_current_context()
   context.add(BlockWrites(["tests/**"]))
   context.add(BlockReads([".env", "secrets/**"]))
   context.add(Limit(RequireTests(), max_in_a_row=3))
   aa.run(context)
   ```

3. Install the hooks for your harness:

   ```bash
   agent_controls install agent_checks.py --target claude
   ```

   The command writes `.claude/settings.json`. The hook commands use the
   absolute path of the Python interpreter of the virtual environment.

4. Start the agent. When it tries to edit `tests/test_x.py`, the edit is denied
   with a reason. When it tries to stop while tests fail, it continues, at most
   three times.

The [tutorial](docs/tutorial.md) explains each step and shows how to write your
own process.

## Supported harnesses

| Target | Configuration file | Hooks |
| --- | --- | --- |
| `claude` | `.claude/settings.json` | all 9 neutral hooks |
| `vscode` | `.github/hooks/agent-controls-vscode.json` | all except `session-end` |
| `copilot-cli` | `.github/hooks/agent-controls-copilot-cli.json` | all except `subagent-start` and `pre-compact` |

[docs/data-model.md](docs/data-model.md) lists the verdicts and context channels
per harness and hook.

## Write a process

```python
import agent_controls as aa


class NoTodoInFinalAnswer(aa.StopProcess):
    """Keeps the agent working while its last message mentions TODO, at most twice."""

    def __init__(self, max_reminders: int = 2) -> None:
        self.max_reminders = max_reminders

    def __state__(self) -> None:
        self.reminders = 0

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        if "TODO" in (event.last_message or "") and self.reminders < self.max_reminders:
            self.reminders += 1
            aa.log(f"reminder {self.reminders}")
            return aa.block("Your answer mentions TODO. Finish the open items first.")
        return aa.allow()
```

- Extend the family class of the hook: `PreToolProcess`, `PostToolProcess`,
  `PromptProcess`, `StopProcess`, `StartProcess` or `EventProcess`.
- Set state attributes in `__state__`. Do not set them in `__init__`.
- Give a reason with each `block` or `ask`. The agent reads it.

## Session files

```text
.hooks/
    flags.json                           flags for all sessions (context.flags)
    20260915T100000000_3f1c9a2e/        <UTC timestamp>_<short session id>
        session.json
        flags.json                       flags for this session (context.session_flags)
        main-agent/
            state.json                   state, inputs and outputs per step and process
            io.json                      raw stdin, stdout and exit code per step
            log.txt                      agent_controls.log() lines
        Explore_20260915T100512345/      one folder per subagent
```

Replay a recorded call with `agent_controls run agent_checks.py --harness claude
--hook pre-tool --input payload.json`.

## CLI

| Command | Purpose |
| --- | --- |
| `agent_controls run RUNNER --harness H --hook K [--input FILE]` | Run one hook call. The harness calls this. |
| `agent_controls install RUNNER [--target H] [--timeout S]` | Write the hook configuration. Asks for the harness when `--target` is missing. |
| `agent_controls sessions` | List recorded sessions, newest first. |
| `agent_controls hcm init [--dev [PATH]]` | Register the agent bundle of the package in the [hcm](#agent-skills) registry. |
| `agent_controls hcm update [HCM OPTIONS]` | Register the bundle of the installed package version, then run `hcm update agent-controls` in the project. |
| `agent_controls skills [--dest DIR]` | Copy the agent skills without hcm (default `.claude/skills`). |

## Agent skills

The package contains an [hcm](https://github.com/fleskovar/harness_config_manager)
bundle with the name `agent-controls`. It gives an AI agent the skills to install
Agent Controls in a project of any language, to configure the checks, and to write
new processes.

| Skill | Content |
| --- | --- |
| `agent-controls-setup` | Install the package, register the hooks, upgrade, and find the cause of a hook problem. |
| `agent-controls-guardrails` | Tests, a coverage floor, lint, format and protected files. Runner templates for C#, Odin, Julia and Python, and `coverage_floor.py` for Cobertura and LCOV reports. |
| `agent-controls-processes` | Write and test a new process class. The reference of the included processes. |

```bash
python -m agent_controls hcm init            # one time for each machine: register the bundle
hcm install agent-controls -t claude-code    # in each project; also `copilot` and `copilot-cli`
```

After an upgrade of the package, update the bundle in each project:

```bash
python -m agent_controls hcm update -t claude-code --no-prompt
```

The commands need the `hcm` command: `npm install -g harness-config-manager`.

To work on the bundle, register the working copy with `python -m agent_controls
hcm init --dev`. hcm then reads `src/agent_controls/hcm_bundle/` in place, and
`hcm update agent-controls` in a test project installs each edit. `make test`
loads each runner template in each harness, and compares the bundle version with
the package version. Change the two versions together. When hcm is installed,
`make test` also checks the bundle with `hcm validate` and `hcm refs check`.

## Documentation

- [Tutorial](docs/tutorial.md)
- [Included processes](docs/processes.md)
- [Examples](examples/README.md): runner files that use flags, conditions and
  git snapshots
- [Architecture and design](docs/architecture.md)
- [Data model per harness](docs/data-model.md)
- [Add a harness](docs/adding-a-harness.md)
- [Requirements](docs/requirements.md), including known limitations

## Development

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; use .venv/bin/activate on Linux and macOS
pip install -e .[dev]

make test                         # lint, type check and all tests: what CI runs
make test-unit                    # the fast loop
make test-cases                   # the human-readable hook cases
make test-case CASE=claude-edit-of-protected-test-is-denied
make debug-case CASE=claude-edit-of-protected-test-is-denied
make debug-test K=test_most_restrictive_verdict_wins
```

Each folder in `tests/protected/cases/` is one behaviour: `inputs/`, `outputs/` and a
`README.md` walkthrough. The [case index](tests/protected/cases/README.md) lists all of
them and what each one pins. To add a case, add a folder. In VS Code, the launch
configuration "Debug one hook case" runs one case under the debugger.

The development plan and its progress are on the light-plan board in `.lpm/`
(`lpm ui`).
