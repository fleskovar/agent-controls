import agent_actions as aa
from agent_actions.processes import CommandOutcome, RequireTests


def passing_pytest(command, cwd, timeout, stdin):
    """A fake test run where everything passes."""
    return CommandOutcome(exit_code=0, output="5 passed")


context = aa.get_current_context()
context.add(
    RequireTests(
        ["pytest", "-q"],
        on=[aa.Hook.SUBAGENT_STOP],
        command_runner=passing_pytest,
    )
)
aa.run(context)
