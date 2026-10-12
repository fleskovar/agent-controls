import agent_actions as aa
from agent_actions.processes import BlockReads

context = aa.get_current_context()
context.add(BlockReads([".env", "secrets/**"]))
aa.run(context)
