import agent_controls as aa
from agent_controls.processes import CommandOutcome, RunCommand


def failing_dotnet_test(command, cwd, timeout, stdin):
    """A fake C# test run with one failed test."""
    return CommandOutcome(
        exit_code=1,
        output="Failed PricingTests.Discount_is_ten_percent [12 ms]\n"
        "Failed!  - Failed: 1, Passed: 4, Skipped: 0, Total: 5",
    )


context = aa.get_current_context()
context.add(RunCommand("dotnet test --nologo", command_runner=failing_dotnet_test))
aa.run(context)
