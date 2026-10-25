import agent_controls as aa
from agent_controls.processes import RevertWrites

context = aa.get_current_context()
context.add(RevertWrites(["tests/**"]))
aa.run(context)
