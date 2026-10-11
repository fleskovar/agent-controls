import agent_actions as aa
from agent_actions.processes import RevertWrites

context = aa.get_current_context()
context.add(RevertWrites(["tests/**"]))
aa.run(context)
