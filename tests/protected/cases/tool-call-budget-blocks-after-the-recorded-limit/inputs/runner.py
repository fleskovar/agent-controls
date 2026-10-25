import agent_controls as aa
from agent_controls.processes import ToolCallBudget

context = aa.get_current_context()
context.add(ToolCallBudget(3))
aa.run(context)
