import agent_actions as aa
from agent_actions.processes import CommandOutcome, LoopGuard, RequireTests


def failing_pytest(command, cwd, timeout, stdin):
    """A fake test run that always fails, as in the two recorded attempts before."""
    return CommandOutcome(exit_code=1, output="1 failed, 4 passed")


context = aa.get_current_context()
context.add(LoopGuard(RequireTests(["pytest", "-q"], command_runner=failing_pytest), max_blocks=2))
aa.run(context)
