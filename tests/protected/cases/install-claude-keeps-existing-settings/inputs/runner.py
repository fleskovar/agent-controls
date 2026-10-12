import agent_actions as aa
from agent_actions.processes import BlockWrites, LoopGuard, RequireTests

context = aa.get_current_context()
context.add(BlockWrites(["tests/**"]))
context.add(LoopGuard(RequireTests(), max_blocks=3))
aa.run(context)
