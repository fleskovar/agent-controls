import agent_actions as aa
from agent_actions.processes import CommandOutcome, RequireTests


def failing_pytest(command, cwd, timeout, stdin):
    """A fake test run. This case pins the stop rule, not the subprocess handling."""
    return CommandOutcome(exit_code=1, output="1 failed, 4 passed")


context = aa.get_current_context()
context.add(RequireTests(["pytest", "-q"], command_runner=failing_pytest))
aa.run(context)
