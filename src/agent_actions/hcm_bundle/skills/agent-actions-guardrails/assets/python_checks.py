"""The agent checks of a Python project. Copy this file to `.hooks/agent_checks.py`.

Register the hooks again after each change of the process list:

    python -m agent_actions install .hooks/agent_checks.py --target claude --timeout 900

- Before and after each tool call: protect the paths in PROTECTED.
- After each edit of a Python file: `ruff format`, then the tests that the change affects.
- When the session starts: measure the coverage. It is the baseline of the session.
- When the agent wants to stop: `ruff check`, the type check, and all tests. The
  coverage must not be below the baseline.

The commands use the interpreter that runs the hook. Thus ruff, mypy, pytest,
pytest-cov and pytest-testmon must be in the same virtual environment as agent_actions.
"""

import os
import sys

import agent_actions as aa
from agent_actions.processes import (
    BlockWrites,
    CheckAfterEdit,
    Limit,
    PytestCoverage,
    RequireCommand,
    RevertWrites,
)

PYTHON = sys.executable
SOURCE_FILES = ("*.py",)
# The folders that `ruff check` reads when the agent stops.
LINT_PATHS = ("src", "tests")
# The import name of the package that the coverage gate measures.
COVERAGE_PACKAGE = "my_package"
# The coverage baseline. None: the coverage at the session start. A number: a fixed
# minimum in percent, for example 80. The stop is blocked below the baseline.
COVERAGE_MINIMUM: float | None = None
# The message for the agent, and the patterns that it covers. Patterns are relative
# to the project root, and `*` also matches `/`. No patterns: no protection.
PROTECTED: dict[str, list[str]] = {
    # "Only a person changes these tests. Fix the code, not the test.": ["tests/protected/**"],
    # "These files set the dependencies and the checks. Ask the user to change them.": [
    #     "pyproject.toml",
    #     ".hooks/*.py",
    # ],
}

# pytest-testmon needs the C tracer of coverage. With the default tracer of Python
# 3.14 (sys.monitoring), it records incomplete dependencies and skips affected tests.
os.environ["COVERAGE_CORE"] = "ctrace"

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

# 2. After each edit of a Python file: format it, then run the tests that it affects.
#    The affected tests give the feedback early, so no test run is necessary at the start.
context.add(
    CheckAfterEdit(
        [PYTHON, "-m", "ruff", "format", "{paths}"], patterns=SOURCE_FILES, name="format"
    )
)
context.add(
    CheckAfterEdit(
        [PYTHON, "-m", "pytest", "--testmon", "-q"],
        patterns=SOURCE_FILES,
        reason="Make these tests pass before you finish. Do not change or delete tests.",
        name="affected-tests",
    )
)

# 3. When the agent wants to stop. Limit allows the stop after 3 blocked stops
#    in a row, so the agent cannot loop.
context.add(
    Limit(RequireCommand([PYTHON, "-m", "ruff", "check", *LINT_PATHS], name="lint"), max_in_a_row=3)
)
context.add(
    Limit(
        RequireCommand(
            [PYTHON, "-m", "mypy"],
            reason="Fix the type errors. Do not add `# type: ignore`.",
            name="types",
        ),
        max_in_a_row=3,
    )
)
#    The coverage gate also fails when a test fails. Without a fixed minimum, its
#    baseline process runs all tests when the session starts.
session = context.session_flags if COVERAGE_MINIMUM is None else None
coverage = PytestCoverage(
    session, minimum=COVERAGE_MINIMUM, source=COVERAGE_PACKAGE, name="tests-and-coverage"
)
if session is not None:
    context.add(coverage.baseline())
context.add(Limit(coverage, max_in_a_row=3))

aa.run(context)
