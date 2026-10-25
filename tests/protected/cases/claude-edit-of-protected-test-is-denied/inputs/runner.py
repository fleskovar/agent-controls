import agent_controls as aa
from agent_controls.processes import BlockWrites

context = aa.get_current_context()
context.add(BlockWrites(["tests/**", "pyproject.toml"]))
aa.run(context)
