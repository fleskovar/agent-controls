import agent_controls as aa
from agent_controls.processes import BlockReads

context = aa.get_current_context()
context.add(BlockReads([".env", "secrets/**"]))
aa.run(context)
