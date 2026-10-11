"""The agent checks of a Julia package. Copy this file to `.hooks/agent_checks.py`.

Register the hooks again after each change of the process list:

    python -m agent_actions install .hooks/agent_checks.py --target claude --timeout 1200

- Before and after each tool call: protect the paths in PROTECTED.
- When a session starts: show the tests that fail already.
- After each edit of a Julia file: JuliaFormatter on that file.
- When the agent wants to stop: the format check, then all tests with a coverage floor.

The commands need the JuliaFormatter and Coverage packages in the default
environment of Julia, not in the environment of the project:

    julia -e "using Pkg; Pkg.add(ARGS)" JuliaFormatter Coverage
"""

import sys
from pathlib import Path

import agent_actions as aa
from agent_actions.processes import (
    BlockWrites,
    CheckAfterEdit,
    LoopGuard,
    RequireCommand,
    RevertWrites,
    RunCommand,
)

SOURCE_FILES = ("*.jl",)
JULIA = ["julia", "--startup-file=no"]
TESTS = [*JULIA, "--project", "-e", "using Pkg; Pkg.test()"]
# Line coverage of `src` in percent. The stop is blocked below it. Measure the
# project, then set it.
COVERAGE_FLOOR = 80
COVERAGE_REPORT = ".hooks/coverage/lcov.info"
COVERAGE_SCRIPT = str(Path(__file__).with_name("coverage_floor.py"))
# Julia writes one `.cov` file for each source file and process. Coverage.jl merges
# them into one LCOV report. The clean-up before the tests removes the files of an
# earlier run that failed.
TESTS_WITH_COVERAGE = (
    "using Coverage, Pkg; "
    'clean_folder("src"); '
    "Pkg.test(coverage=true); "
    "mkpath(dirname(ARGS[1])); "
    'LCOV.writefile(ARGS[1], process_folder("src")); '
    'clean_folder("src")'
)
# The message for the agent, and the patterns that it covers. Patterns are relative
# to the project root, and `*` also matches `/`. No patterns: no protection.
PROTECTED: dict[str, list[str]] = {
    # "Only a person changes these tests. Fix the code, not the test.": ["test/protected/**"],
    # "These files set the dependencies and the checks. Ask the user to change them.": [
    #     "Project.toml",
    #     ".JuliaFormatter.toml",
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

# 3. After each edit of a Julia file: format the file.
context.add(
    CheckAfterEdit(
        [*JULIA, "-e", "using JuliaFormatter; format(ARGS)", "{paths}"],
        patterns=SOURCE_FILES,
        name="format",
    )
)

# 4. When the agent wants to stop. LoopGuard allows the stop after 3 blocked stops
#    in a row, so the agent cannot loop.
context.add(
    LoopGuard(
        RequireCommand(
            [
                *JULIA,
                "-e",
                "using JuliaFormatter; exit(format(ARGS; overwrite=false) ? 0 : 1)",
                "src",
                "test",
            ],
            reason='Format the files: julia -e "using JuliaFormatter; format(ARGS)" src test',
            name="format-check",
        )
    )
)
context.add(
    LoopGuard(
        RequireCommand(
            [
                sys.executable,
                COVERAGE_SCRIPT,
                str(COVERAGE_FLOOR),
                COVERAGE_REPORT,
                "--",
                *JULIA,
                "--project",
                "-e",
                TESTS_WITH_COVERAGE,
                COVERAGE_REPORT,
            ],
            reason=(
                f"Make all tests pass and keep the line coverage at {COVERAGE_FLOOR} % or more. "
                "Add tests for the new code. Do not change or delete tests."
            ),
            timeout=900.0,
            name="tests-and-coverage",
        )
    )
)

aa.run(context)
