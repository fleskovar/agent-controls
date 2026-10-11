import agent_actions as aa
from agent_actions.processes import RevertWrites

context = aa.get_current_context()
context.add(RevertWrites(["tests/**"], on=[aa.Hook.POST_TOOL]))
aa.run(context)
