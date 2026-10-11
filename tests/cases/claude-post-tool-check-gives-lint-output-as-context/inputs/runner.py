import agent_actions as aa
from agent_actions.processes import CheckAfterEdit, CommandOutcome


def failing_ruff(command, cwd, timeout, stdin):
    """A fake linter run with one finding, so the case stays deterministic."""
    return CommandOutcome(exit_code=1, output="src/pricing.py:12:1: E501 line too long (118 > 100)")


context = aa.get_current_context()
context.add(CheckAfterEdit("ruff check {paths}", patterns=["*.py"], command_runner=failing_ruff))
aa.run(context)
