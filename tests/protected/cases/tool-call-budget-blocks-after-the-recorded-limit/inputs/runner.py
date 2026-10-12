import agent_actions as aa
from agent_actions.processes import ToolCallBudget

context = aa.get_current_context()
context.add(ToolCallBudget(3))
aa.run(context)
