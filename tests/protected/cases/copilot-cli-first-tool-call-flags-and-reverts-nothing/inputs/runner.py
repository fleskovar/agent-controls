import agent_controls as aa
from agent_controls.processes import RevertWrites

context = aa.get_current_context()
context.add(RevertWrites(["tests/**"], on=[aa.Hook.POST_TOOL]))
aa.run(context)
