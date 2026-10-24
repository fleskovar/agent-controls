"""The agent checks of a C# project. Copy this file to `.hooks/agent_checks.py`.

Register the hooks again after each change of the process list:

    python -m agent_actions install .hooks/agent_checks.py --target claude --timeout 1200

- Before and after each tool call: protect the paths in PROTECTED.
- When a session starts: show the tests that fail already, and measure the
  coverage. It is the baseline of the session.
- After each edit of a C# file: `dotnet format whitespace` on that file.
- When the agent wants to stop: the format check, the build with warnings as
  errors, then all tests. The coverage must not be below the baseline.

The commands run in the project root. They need a solution or a project file there.
"""

import agent_actions as aa
from agent_actions.processes import (
    BlockWrites,
    CheckAfterEdit,
    DotnetCoverage,
    Limit,
    RequireCommand,
    RevertWrites,
    RunCommand,
)

SOURCE_FILES = ("*.cs",)
TESTS = ["dotnet", "test", "--nologo"]
# The line coverage baseline. None: the coverage at the session start. A number: a
# fixed minimum in percent, for example 80. The stop is blocked below the baseline.
COVERAGE_MINIMUM: float | None = None
# The message for the agent, and the patterns that it covers. Patterns are relative
# to the project root, and `*` also matches `/`. No patterns: no protection.
PROTECTED: dict[str, list[str]] = {
    # "Only a person changes these tests. Fix the code, not the test.": ["tests/Protected/**"],
    # "These files set the build and the analyzers. Ask the user to change them.": [
    #     "Directory.Build.props",
    #     ".editorconfig",
    #     ".hooks/*.py",
    # ],
}

context = aa.get_current_context()


def with_context(*hooks: aa.Hook) -> list[aa.Hook]:
    """The hooks that this harness has and that can give context to the agent."""
    capabilities = context.adapter.capabilities
    return [hook for hook in hooks if hook in capabilities and capabilities[hook].context]


# 1. Protected paths. BlockWrites denies a write tool before the change. RevertWrites
#    uses git to revert a change that a shell command made.
for number, (reason, patterns) in enumerate(PROTECTED.items(), start=1):
    context.add(BlockWrites(patterns, reason=reason, name=f"protect-{number}"))
    context.add(
        RevertWrites(
            patterns,
            on=with_context(aa.Hook.SESSION_START, aa.Hook.SUBAGENT_START, aa.Hook.POST_TOOL),
            name=f"revert-{number}",
        )
    )

# 2. When a session starts: the agent reads the failures before it works.
start_hooks = with_context(aa.Hook.SESSION_START)
if start_hooks:
    context.add(RunCommand(TESTS, on=start_hooks, name="tests-at-start"))

# 3. After each edit of a C# file: format the file. `--folder` reads no project file,
#    so the command is fast and it accepts the absolute paths that the harness gives.
context.add(
    CheckAfterEdit(
        ["dotnet", "format", "whitespace", "--folder", "--include", "{paths}"],
        patterns=SOURCE_FILES,
        name="format",
    )
)

# 4. When the agent wants to stop. Limit allows the stop after 3 blocked stops
#    in a row, so the agent cannot loop.
context.add(
    Limit(
        RequireCommand(
            ["dotnet", "format", "--verify-no-changes"],
            reason="Run `dotnet format`. Then fix the problems that it cannot fix.",
            name="format-check",
        ),
        max_in_a_row=3,
    )
)
context.add(
    Limit(
        RequireCommand(
            ["dotnet", "build", "--nologo", "-warnaserror"],
            reason="Fix the errors and the warnings. Do not disable or suppress a warning.",
            name="build",
        ),
        max_in_a_row=3,
    )
)
#    The coverage gate also fails when a test fails. coverlet.collector, which the
#    test templates of .NET include, writes one report for each test project into
#    .hooks/coverage. The gate merges them. Without a fixed minimum, its baseline
#    process runs all tests a second time when the session starts.
session = context.session_flags if COVERAGE_MINIMUM is None else None
coverage = DotnetCoverage(session, minimum=COVERAGE_MINIMUM, name="tests-and-coverage")
if session is not None:
    context.add(coverage.baseline())
context.add(Limit(coverage, max_in_a_row=3))

aa.run(context)
