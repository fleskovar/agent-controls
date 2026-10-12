import agent_actions as aa
from agent_actions.processes import CommandOutcome, RequireCommand


def failing_ruff(command, cwd, timeout, stdin):
    """A fake linter run with one finding."""
    return CommandOutcome(exit_code=1, output="src/app.py:3:1: F401 'os' imported but unused")


context = aa.get_current_context()
context.add(
    RequireCommand(
        ["ruff", "check", "."],
        on=[aa.Hook.SUBAGENT_STOP],
        name="lint",
        command_runner=failing_ruff,
    )
)
aa.run(context)
