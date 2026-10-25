import json

import agent_controls as aa
from agent_controls.processes import CheckAfterEdit, CommandOutcome


def failing_dotnet_test(command, cwd, timeout, stdin):
    """A stand-in for a test command. It reads the hook event, as a real command reads stdin."""
    event = json.loads(stdin)
    tool = event["tool"]
    return CommandOutcome(
        exit_code=1,
        output=f"{event['harness']} {event['hook']}: {tool['name']} ({tool['kind']}) on {tool['paths'][0]}\n"
        "Failed PricingTests.Discount_is_ten_percent",
    )


context = aa.get_current_context()
context.add(
    CheckAfterEdit("dotnet test --nologo", patterns=["*.cs"], command_runner=failing_dotnet_test)
)
aa.run(context)
