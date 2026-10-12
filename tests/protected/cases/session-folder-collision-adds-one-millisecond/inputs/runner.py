import agent_actions as aa
from agent_actions.processes import AddContext

context = aa.get_current_context()
context.add(AddContext("Run the tests with `make test`."))
aa.run(context)
