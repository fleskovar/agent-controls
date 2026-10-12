import agent_actions as aa
from agent_actions.processes import BlockWrites

context = aa.get_current_context()
context.add(BlockWrites(["tests/**", "pyproject.toml"]))
aa.run(context)
