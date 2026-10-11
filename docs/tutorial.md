# Tutorial: from install to your own guardrail

This tutorial takes about 30 minutes. You add guardrails to a project, watch them
work, read the session record, and write one process of your own.

You need Python 3.11 or later, and one of: Claude Code, VS Code with the GitHub
Copilot agent, or GitHub Copilot CLI.

## Step 1: Install the package

Install it into the virtual environment of your project, not globally. The hook
command uses the interpreter that runs `install`, so the virtual environment must
be the one that has the package.

```bash
cd my-project
python -m venv .venv
.venv/Scripts/activate           # Windows. Linux and macOS: source .venv/bin/activate
pip install git+https://github.com/fleskovar/agent_actions
```

Check the command:

```bash
agent_actions --help
```

## Step 2: Write the runner file

Create `agent_checks.py` in the project root:

```python
import agent_actions as aa
from agent_actions.processes import BlockReads, BlockWrites, LoopGuard, RequireTests

context = aa.get_current_context()

# Nobody edits the tests except a person.
context.add(BlockWrites(["tests/**"]))

# The agent never reads credentials.
context.add(BlockReads([".env", "secrets/**"]))

# The agent does not finish while the tests fail, but it does not retry for ever.
context.add(LoopGuard(RequireTests(), max_blocks=3))

aa.run(context)
```

Three rules for this file:

1. Call `aa.run(context)` once, at the end.
2. Never read stdin and never print. The CLI does both.
3. Never branch on the harness. The file stays the same for all three.

## Step 3: Install the hooks

```bash
agent_actions install agent_checks.py --target claude
```

Output:

```text
Installed 2 hook(s) for claude: pre-tool, stop
Configuration file: C:\my-project\.claude\settings.json
```

The command derives the hooks from the processes: `BlockWrites` and `BlockReads`
need `pre-tool`, and the loop guard needs `stop`. Other settings in the file stay
unchanged. Run the command again after you add or remove a process.

Without `--target`, the command asks which harness to use.

## Step 4: Watch a guardrail work

Start the agent and ask it to change a test, for example: "make the failing
assertion in tests/test_pricing.py pass by changing the expected value".

The agent tries an edit. The hook denies it, and the agent reads:

```text
[BlockWrites] 'Edit' on 'C:\my-project\tests\test_pricing.py' is blocked:
'tests/**' is protected. These files are protected. Do not change them.
If a change is necessary, stop and ask the user.
```

A good agent then fixes the code instead, which is the point of the reason text.

## Step 5: Read the session record

```bash
agent_actions sessions
```

```text
20260915T100000000_3f1c9a2e  session=3f1c9a2e-77b0-4c1d-9d0e-5a4b3c2d1e0f  agents=main-agent
```

Inside `.hooks/20260915T100000000_3f1c9a2e/main-agent/`:

| File | Content |
| --- | --- |
| `state.json` | Per timestamp and process: the state, the input and the output. |
| `io.json` | Per timestamp: the raw stdin, the stdout and the exit code. |
| `log.txt` | Your `aa.log(...)` lines, and one summary line per result. |

Copy one `stdin` object from `io.json` into `payload.json`, and replay the call
with no agent:

```bash
agent_actions run agent_checks.py --harness claude --hook pre-tool --input payload.json
```

This is the fastest way to debug a guardrail, and it is how you build a test case
from a real session.

## Step 6: Write your own process

A process is a class with a `run` method. Pick the family of the hook you need:
`PreToolProcess`, `PostToolProcess`, `PromptProcess`, `StopProcess`,
`StartProcess` or `EventProcess`.

This one keeps the agent working while its final message still says TODO, but no
more than twice:

```python
# no_todo.py
import agent_actions as aa


class NoTodoInFinalAnswer(aa.StopProcess):
    """Blocks a stop while the last message mentions TODO."""

    def __init__(self, max_reminders: int = 2) -> None:
        self.max_reminders = max_reminders

    def __state__(self) -> None:
        self.reminders = 0

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        message = event.last_message or ""
        if "TODO" not in message or self.reminders >= self.max_reminders:
            return aa.allow()
        self.reminders += 1
        aa.log(f"reminder {self.reminders} of {self.max_reminders}")
        return aa.block(
            "Your answer still says TODO. Finish the open items, "
            "or tell the user why they stay open."
        )
```

Add it to the runner file:

```python
from no_todo import NoTodoInFinalAnswer

context.add(NoTodoInFinalAnswer())
```

The runner file imports modules that sit next to it, so `no_todo.py` needs no
package.

Four rules to follow:

- **Give every `block` and `ask` a reason.** It is the only text the agent reads.
- **Declare state in `__state__`, not in `__init__`.** The attributes that
  `__state__` creates are restored before each call and recorded after it.
  `__init__` holds configuration.
- **Take a parameter instead of reading the clock, the environment or a file.**
  Your tests then need no mocking.
- **Return a result. Never print.** Use `aa.log(...)` for the session log.

## Step 7: Test it

```python
# tests/test_no_todo.py
from agent_actions.model import Harness, Hook, HookInput, Verdict
from no_todo import NoTodoInFinalAnswer


def test_todo_in_the_final_message_blocks_the_stop() -> None:
    process = NoTodoInFinalAnswer()
    process.load_state({})
    event = HookInput(Harness.CLAUDE, Hook.STOP, last_message="Done. TODO: error handling.")

    result = process.run(event)

    assert result.verdict is Verdict.BLOCK
    assert process.dump_state() == {"reminders": 1}


def test_the_third_stop_is_allowed() -> None:
    process = NoTodoInFinalAnswer(max_reminders=2)
    process.load_state({"reminders": 2})
    event = HookInput(Harness.CLAUDE, Hook.STOP, last_message="Still TODO.")

    assert process.run(event).verdict is Verdict.ALLOW
```

Break the rule on purpose once and watch the test fail. A test you never saw fail
is a test you have not tested.

## Step 8: Know what a harness cannot do

`context.add` rejects a process that cannot work in the target harness, and the
message says why. Three cases you meet in practice:

```text
Cannot add process 'AddContext' for harness 'claude': 'stop' has no channel for context.
Cannot add process 'PromptFilter' for harness 'copilot-cli': 'user-prompt' cannot deliver the verdicts block.
Cannot add process 'Greeting' for harness 'copilot-cli': harness 'copilot-cli' has no 'subagent-start' hook.
```

The full table is in [data-model.md](data-model.md). A mistake that these checks
cannot see, a process that returns a verdict it never declared, fails during the
run with exit code 1 and a message on stderr. It never reaches the agent as
silence.

## Where to go next

- [Included processes](processes.md), with every parameter.
- [Architecture](architecture.md), for the reason behind each design decision.
- `python -m agent_actions hcm init`, then `hcm install agent-actions -t claude-code`,
  installs the skills that teach an AI agent to set up Agent Actions, to configure
  checks for a project of any language, and to write processes. The
  [README](../README.md#agent-skills) has the details.
