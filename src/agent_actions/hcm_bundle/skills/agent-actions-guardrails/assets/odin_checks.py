"""The agent checks of an Odin project. Copy this file to `.hooks/agent_checks.py`.

Register the hooks again after each change of the process list:

    python -m agent_actions install .hooks/agent_checks.py --target claude --timeout 600

- Before and after each tool call: protect the paths in PROTECTED.
- When a session starts: show the tests that fail already.
- After each edit of an Odin file: `odin check` with the vet flags.
- When the agent wants to stop: `odin check`, then all tests. A memory leak or a
  bad free in a test is a failure.

Odin has no formatter and no coverage tool in the compiler. The vet flags are the
linter. For a coverage floor, see the Odin page of the agent-actions-guardrails skill.
"""

import agent_actions as aa
from agent_actions.processes import (
    BlockWrites,
    CheckAfterEdit,
    Limit,
    RequireCommand,
    RevertWrites,
    RunCommand,
)

SOURCE_FILES = ("*.odin",)
# The folder of the package that `odin check` reads, and the folder of the test packages.
PACKAGE = "."
TEST_PACKAGES = "tests"
# The vet flags of the project. Use the same flags as the build script and the CI.
VET = ["-vet", "-strict-style", "-vet-tabs", "-disallow-do", "-warnings-as-errors"]
# Add "-no-entry-point" when the package is a library without a `main` procedure.
CHECK = ["odin", "check", PACKAGE, *VET]
TESTS = [
    "odin",
    "test",
    TEST_PACKAGES,
    "-all-packages",
    *VET,
    "-define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true",
]
CHECK_REASON = "Fix the errors. Do not remove a vet flag, and do not add `#+vet` exceptions."
# The message for the agent, and the patterns that it covers. Patterns are relative
# to the project root, and `*` also matches `/`. No patterns: no protection.
PROTECTED: dict[str, list[str]] = {
    # "Only a person changes these tests. Fix the code, not the test.": ["tests/protected/**"],
    # "These files set the build and the checks. Ask the user to change them.": [
    #     "build.bat",
    #     "build.sh",
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

# 3. After each edit of an Odin file: the type check and the vet rules. `odin check`
#    generates no code, so it is fast enough to run after each edit.
context.add(CheckAfterEdit(CHECK, patterns=SOURCE_FILES, reason=CHECK_REASON, name="check"))

# 4. When the agent wants to stop. Limit allows the stop after 3 blocked stops
#    in a row, so the agent cannot loop.
context.add(Limit(RequireCommand(CHECK, reason=CHECK_REASON, name="vet"), max_in_a_row=3))
context.add(
    Limit(
        RequireCommand(
            TESTS,
            reason=(
                "Make all tests pass, with no memory leak and no bad free. "
                "Add tests for the new code. Do not change or delete tests."
            ),
            name="tests",
        ),
        max_in_a_row=3,
    )
)

aa.run(context)
