import agent_actions as aa
from agent_actions.processes import BlockWrites, CheckAfterEdit

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(CheckAfterEdit("ruff check {paths}", patterns=["*.py"]))
aa.run(context)
