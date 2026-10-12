"""Included processes: guardrails and checks that work in every supported harness."""

from agent_actions.processes.commands import (
    CheckAfterEdit,
    CommandOutcome,
    RequireCommand,
    RequireTests,
    RunCommand,
    run_subprocess,
)
from agent_actions.processes.context import AddContext
from agent_actions.processes.flags import (
    SetFlag,
    changed_paths,
    clear_on_pass,
    git_snapshot,
    on_changed_paths,
)
from agent_actions.processes.limits import LoopGuard, ToolCallBudget
from agent_actions.processes.paths import BlockReads, BlockWrites, PathGuard, RevertWrites
from agent_actions.processes.shell import BlockShellCommands

__all__ = [
    "AddContext",
    "BlockReads",
    "BlockShellCommands",
    "BlockWrites",
    "CheckAfterEdit",
    "CommandOutcome",
    "LoopGuard",
    "PathGuard",
    "RequireCommand",
    "RequireTests",
    "RevertWrites",
    "RunCommand",
    "SetFlag",
    "ToolCallBudget",
    "changed_paths",
    "clear_on_pass",
    "git_snapshot",
    "on_changed_paths",
    "run_subprocess",
]
