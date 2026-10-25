"""Processes that limit loops and tool use."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

from agent_controls.model import (
    Capability,
    Hook,
    HookInput,
    ProcessResult,
    ToolKind,
    Verdict,
    allow,
    block,
)
from agent_controls.process import ALLOW_ONLY, ALLOW_OR_BLOCK, PreToolProcess, Process, StopProcess
from agent_controls.processes.flags import Flags

INNER_STATE_KEY: Final = "inner"
LOOP_ADVICE: Final = (
    "If the problems remain at your next stop, stop anyway and tell the user "
    "that the approach needs a review."
)
BUDGET_REASON: Final = "Stop now and report your progress and the open problems to the user."
LIMIT_ADVICE: Final[Mapping[Verdict, str]] = {
    Verdict.ALLOW: (
        "This is the last block. Try a different approach. If the problem remains the next "
        "time, the check lets you continue. Then tell the user what you tried, and ask for help."
    ),
    Verdict.ASK: "This is the last block. The next time, the user decides.",
    Verdict.BLOCK: (
        "Your approach does not work. Try a different approach, or ask the user for help."
    ),
}
RESET_REASON: Final = "Reset the count in a row."
_NUMBERS: Final = re.compile(r"0x[0-9a-f]+|\d+", re.IGNORECASE)


def is_block(result: ProcessResult) -> bool:
    return result.verdict is Verdict.BLOCK


def problem_text(result: ProcessResult) -> str:
    """The reasons of a result without numbers. Thus a new duration is not a new problem.

    ponytail: all numbers go, so "1 failed" and "2 failed" are the same problem. The
    names of the failed tests stay, so a different failed test is a new problem. If a
    number is important, give `Limit` a `problem` function that keeps it.
    """
    return _NUMBERS.sub("#", "\n".join(result.reasons))


class _WrapsProcess(Process):
    """Records the state of the wrapped process under `inner`, next to its own state."""

    process: Process

    def load_state(self, saved: Mapping[str, Any]) -> None:
        super().load_state(saved)
        self.process.load_state(saved.get(INNER_STATE_KEY, {}))

    def dump_state(self) -> dict[str, Any]:
        return {**super().dump_state(), INNER_STATE_KEY: self.process.dump_state()}


class Limit(_WrapsProcess):
    """Wraps any process, counts its results, and changes the verdict after a maximum.

    `counts` selects the results to count. The default is each block.
    - `max_in_a_row`: a result that `counts` does not select resets this count.
    - `max_total`: this count never resets. With `window`, it counts only the
      results of the last `window` seconds.

    The result that reaches a maximum gets `message`. Each counted result after a
    maximum gets the verdict `then`:
    - ALLOW releases the check, for example a stop while the tests fail.
    - ASK gives the decision to the user. Only `pre-tool` can deliver it.
    - BLOCK never releases. Use it for a guard that must hold, with a new message.

    More resets of the count in a row:
    - After a release.
    - On each hook in `reset_on`, for example `Hook.USER_PROMPT`: a new prompt is a
      new problem. On a hook that the wrapped process does not use, `Limit` only allows.
    - With `problem`, a function of the result: a new value is a new problem. Use
      `problem_text` to ignore numbers, for example durations.

    The counts are state of the agent. With `store`, a flags dict, they are in that
    dict instead: `context.session_flags` shares them with the subagents, and
    `context.flags` with the later sessions. A person resets them when they delete
    the flag. With `flags` and `flag`, each release also sets that flag.
    """

    def __init__(
        self,
        process: Process,
        *,
        max_in_a_row: int | None = None,
        max_total: int | None = None,
        window: float | None = None,
        then: Verdict = Verdict.ALLOW,
        message: str = "",
        counts: Callable[[ProcessResult], bool] = is_block,
        problem: Callable[[ProcessResult], str] | None = None,
        reset_on: Sequence[Hook] = (),
        store: Flags | None = None,
        flags: Flags | None = None,
        flag: str = "",
        name: str = "",
        clock: Callable[[], float] = time.time,
    ) -> None:
        maxima = [limit for limit in (max_in_a_row, max_total) if limit is not None]
        if not maxima or min(maxima) < 1:
            raise ValueError("Give max_in_a_row, max_total or both, each 1 or more.")
        if window is not None and (max_total is None or window <= 0):
            raise ValueError("`window` needs `max_total`, and must be more than 0 seconds.")
        if (flags is None) != (not flag):
            raise ValueError("Give `flags` and `flag` together.")
        self.process = process
        self.max_in_a_row = max_in_a_row
        self.max_total = max_total
        self.window = window
        self.then = then
        self.message = message or LIMIT_ADVICE[then]
        self.counts = counts
        self.problem = problem
        self.reset_on = tuple(reset_on)
        self.store = store
        self.flags = flags
        self.flag = flag
        self.clock = clock
        self.on = (*process.hooks, *(hook for hook in reset_on if hook not in process.hooks))
        self.name = name or f"Limit({process.label})"
        # Not `self.family = ...`: the type checkers forbid an instance value for a ClassVar.
        vars(self)["family"] = (
            *process.family,
            *(hook for hook in reset_on if hook not in process.family),
        )

    def needs(self, hook: Hook) -> Capability:
        """The needs of the wrapped process plus `then`. A reset hook only allows."""
        inner = self.process.needs(hook)
        return (
            Capability(inner.verdicts | {self.then}, inner.context)
            if hook in self.process.hooks
            else Capability(ALLOW_ONLY, context=False)
        )

    def __state__(self) -> None:
        self.in_a_row = 0
        self.total = 0
        self.problem_id = ""
        self.times: list[float] = []

    def run(self, event: HookInput) -> ProcessResult:
        if self.store is not None:
            Process.load_state(self, self.store.get(self.label, {}))
        if event.hook in self.reset_on:
            self.in_a_row = 0
            self.problem_id = ""
        outcome = (
            self._count(self.process.run(event))
            if event.hook in self.process.hooks
            else allow(RESET_REASON)
        )
        if self.store is not None:
            # ponytail: two agents that count at the same moment can lose a count, because
            # the last write of the flag wins. Lock the flag file if exact counts matter.
            self.store[self.label] = Process.dump_state(self)
        return outcome

    def _count(self, result: ProcessResult) -> ProcessResult:
        if self.counts(result):
            if self.problem is not None:
                problem_id = hashlib.sha256(self.problem(result).encode()).hexdigest()[:16]
                if problem_id != self.problem_id:
                    self.in_a_row = 0
                self.problem_id = problem_id
            self.in_a_row += 1
            self.total += 1
            if self.window is not None:
                now = self.clock()
                self.times = [*(moment for moment in self.times if moment > now - self.window), now]
            outcome = self._limited(result)
        else:
            self.in_a_row = 0
            self.problem_id = ""
            outcome = result
        return outcome

    def _limited(self, result: ProcessResult) -> ProcessResult:
        total, total_scope = (
            (self.total, "in total")
            if self.window is None
            else (len(self.times), f"in the last {self.window:g} s")
        )
        counters = [
            (count, limit, scope)
            for count, limit, scope in (
                (self.in_a_row, self.max_in_a_row, "in a row"),
                (total, self.max_total, total_scope),
            )
            if limit is not None
        ]
        status = (
            "Count: " + ", ".join(f"{c} of {limit} {scope}" for c, limit, scope in counters) + "."
        )
        used_up = [f"{limit} {scope}" for count, limit, scope in counters if count > limit]
        if used_up:
            self.in_a_row = 0
            if self.flags is not None:
                self.flags[self.flag] = True
            outcome = replace(
                result,
                verdict=self.then,
                reasons=(
                    f"The limit of {' and '.join(used_up)} is used up.",
                    self.message,
                    *result.reasons,
                ),
            )
        elif any(count == limit for count, limit, _ in counters):
            outcome = replace(result, reasons=(*result.reasons, status, self.message))
        else:
            outcome = replace(result, reasons=(*result.reasons, status))
        return outcome


class LoopGuard(_WrapsProcess, StopProcess):
    """Wraps a stop process, and allows the stop after `max_blocks` blocks in a row.

    Use it with RequireTests: when the agent cannot make the tests pass in a few
    attempts, the strategy is probably wrong and a person must look at it. The
    last block tells the agent to report this at its next stop.

    Deprecated: use `Limit(process, max_in_a_row=3)`. LoopGuard stays for the runner
    files that use it.
    """

    def __init__(self, process: StopProcess, max_blocks: int = 3, *, name: str = "") -> None:
        if max_blocks < 1:
            raise ValueError("max_blocks must be 1 or more.")
        self.process = process
        self.max_blocks = max_blocks
        self.on = process.hooks
        self.name = name or f"LoopGuard({process.label})"

    def __state__(self) -> None:
        self.consecutive_blocks = 0

    def run(self, event: HookInput) -> ProcessResult:
        result = self.process.run(event)
        if result.verdict is not Verdict.BLOCK:
            self.consecutive_blocks = 0
            outcome = result
        elif self.consecutive_blocks >= self.max_blocks:
            self.consecutive_blocks = 0
            outcome = allow(
                f"Allowed the stop after {self.max_blocks} blocked stops in a row.", *result.reasons
            )
        else:
            self.consecutive_blocks += 1
            outcome = replace(result, reasons=(*result.reasons, self._attempt_note()))
        return outcome

    def _attempt_note(self) -> str:
        note = f"Blocked stop {self.consecutive_blocks} of {self.max_blocks}."
        return f"{note} {LOOP_ADVICE}" if self.consecutive_blocks == self.max_blocks else note


class ToolCallBudget(PreToolProcess):
    """Blocks tool calls after `max_calls` calls by the same agent in a session."""

    verdicts = ALLOW_OR_BLOCK

    def __init__(
        self,
        max_calls: int,
        *,
        kinds: Iterable[ToolKind] = tuple(ToolKind),
        reason: str = BUDGET_REASON,
        name: str = "",
    ) -> None:
        self.max_calls = max_calls
        self.kinds = frozenset(kinds)
        self.reason = reason
        self.name = name

    def __state__(self) -> None:
        self.calls = 0

    def run(self, event: HookInput) -> ProcessResult:
        counted = event.tool is not None and event.tool.kind in self.kinds
        if counted and self.calls >= self.max_calls:
            result = block(f"The budget of {self.max_calls} tool calls is used up. {self.reason}")
        else:
            self.calls += int(counted)
            result = allow(f"{self.calls} of {self.max_calls} tool calls used.")
        return result
