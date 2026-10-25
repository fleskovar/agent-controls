import agent_controls as aa
from agent_controls.processes import BlockWrites, ToolCallBudget

context = aa.get_current_context()
context.add(ToolCallBudget(5))
context.add(BlockWrites(["tests/**"]))
aa.run(context)
