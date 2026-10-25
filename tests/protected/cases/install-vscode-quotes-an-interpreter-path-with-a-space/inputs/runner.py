import agent_controls as aa
from agent_controls.processes import BlockWrites, CheckAfterEdit

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(CheckAfterEdit("ruff check {paths}", patterns=["*.py"]))
aa.run(context)
