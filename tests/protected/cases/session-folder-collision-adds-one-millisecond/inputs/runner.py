import agent_controls as aa
from agent_controls.processes import AddContext

context = aa.get_current_context()
context.add(AddContext("Run the tests with `make test`."))
aa.run(context)
