"""Run the active processes of one hook call and combine their results.

This module does no file I/O. The session store loads the saved states before a
step and records the step after it.
"""

from __future__ import annotations

import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_controls.errors import AgentControlsError, IncompatibleResultError, ProcessFailedError
from agent_controls.model import (
    Capability,
    HookInput,
    NamedResult,
    ProcessResult,
    Verdict,
    block,
    combine,
)
from agent_controls.process import Process
from agent_controls.runtime import capture_log, log_source


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """One process in one step, as state.json stores it."""

    name: str
    state: Mapping[str, Any]
    inputs: Mapping[str, Any]
    outputs: Mapping[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {
            "state": dict(self.state),
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
        }


@dataclass(frozen=True, slots=True)
class Step:
    result: ProcessResult
    records: tuple[ProcessRecord, ...]
    log_lines: tuple[str, ...]


def execute(
    processes: Sequence[Process],
    event: HookInput,
    capability: Capability,
    saved_states: Mapping[str, Mapping[str, Any]],
) -> Step:
    """Restore state, run each process, check its result, and combine the results.

    A process whose `when` condition is false does not run, and gets no record. The
    condition is read immediately before the process. Thus it sees a flag that an
    earlier process set in the same call.
    """
    lines: list[str] = []
    named: list[NamedResult] = []
    records: list[ProcessRecord] = []
    inputs = event.to_record()
    with capture_log(lines):
        for process in processes:
            process.load_state(saved_states.get(process.label, {}))
            result = _run_guarded(process, event, capability, lines)
            if result is None:
                lines.append(f"[{process.label}] skipped: its `when` condition is false")
            else:
                check_result(process, result, event, capability)
                lines.append(_summary(process, result))
                named.append(NamedResult(process.label, result))
                records.append(
                    ProcessRecord(process.label, process.dump_state(), inputs, result.to_record())
                )
    return Step(combine(named), tuple(records), tuple(lines))


def check_result(
    process: Process, result: ProcessResult, event: HookInput, capability: Capability
) -> None:
    """Raise when a result cannot reach the agent. This check keeps failures loud."""
    deliverable = process.needs(event.hook).verdicts & capability.verdicts
    if result.verdict not in deliverable:
        raise IncompatibleResultError(
            f"Process '{process.label}' returned '{result.verdict}' on '{event.hook}' for "
            f"harness '{event.harness}', but only {', '.join(sorted(deliverable))} can reach "
            "the agent there."
        )
    if result.context and not capability.context:
        raise IncompatibleResultError(
            f"Process '{process.label}' returned context on '{event.hook}' for harness "
            f"'{event.harness}', but that hook has no channel for context."
        )


def _run_guarded(
    process: Process, event: HookInput, capability: Capability, lines: list[str]
) -> ProcessResult | None:
    """Run one process, or return None when its `when` condition is false.

    An exception, also from the condition, becomes a block where a block is possible
    (fail closed).
    """
    result: ProcessResult | None = None
    try:
        with log_source(process.label):
            if process.when is None or process.when(event):
                result = process.run(event)
    except AgentControlsError:
        raise
    except Exception as error:
        lines.append(f"[{process.label}] {traceback.format_exc().rstrip()}")
        if Verdict.BLOCK not in capability.verdicts & process.needs(event.hook).verdicts:
            raise ProcessFailedError(
                f"Process '{process.label}' failed on '{event.hook}': "
                f"{type(error).__name__}: {error}"
            ) from error
        result = block(
            f"The check failed with {type(error).__name__}: {error}. "
            "Tell the user. The traceback is in the log.txt file under .hooks/."
        )
    return result


def _summary(process: Process, result: ProcessResult) -> str:
    reasons = " | ".join(result.reasons)
    return f"[{process.label}] {result.verdict}" + (f": {reasons}" if reasons else "")
