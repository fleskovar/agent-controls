"""A coverage gate: the agent cannot stop while the coverage is below a baseline.

The baseline is the coverage at the start of the session, or a fixed minimum. A
command of the project measures the coverage, in any language. A regular
expression reads the percentage from the command output, or the gate reads the
Cobertura or LCOV reports that the command writes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Final

from agent_controls.model import Hook, HookInput, ProcessResult, allow, block
from agent_controls.process import StopProcess
from agent_controls.processes.commands import (
    DEFAULT_MAX_OUTPUT_CHARS,
    PYTEST_COMMAND,
    Command,
    CommandOutcome,
    CommandRunner,
    display,
    event_json,
    run_subprocess,
    tail,
    working_dir,
)
from agent_controls.processes.flags import Flags, SetFlag

PERCENT_PATTERN: Final = r"(\d+(?:\.\d+)?)\s*%"
# pytest-cov: "TOTAL    1312    992  24.39%"
PYTEST_PATTERN: Final = r"^TOTAL\s.*?(\d+(?:\.\d+)?)%"
# The text-summary reporter of istanbul, which Vitest and Jest use: "Lines : 85.71% ( 6/7 )"
ISTANBUL_PATTERN: Final = r"^Lines\s*:\s*(\d+(?:\.\d+)?)%"
VITEST_COMMAND: Final = "npx vitest run --coverage --coverage.reporter=text-summary"
DOTNET_RESULTS: Final = ".hooks/coverage"
COVERAGE_REASON: Final = (
    "Add tests for the new code, or delete the code that no test runs. "
    "Do not change or delete tests."
)

LineKey = tuple[str, int]


class RequireCoverage(StopProcess):
    """Blocks the stop when the coverage is below the baseline, or when the command fails.

    Give `flags` (usually `context.session_flags`) to compare with the coverage at
    the session start. Then also add `baseline()`, which measures it. Or give a
    fixed `minimum` in percent, and no flags.

    The coverage is the last match of `pattern` in the command output. The pattern
    has one group: the number. With `reports`, a glob relative to the project root,
    the gate instead reads the line coverage of the Cobertura or LCOV reports that
    match. It deletes these reports before each run, so an old report never passes.
    """

    def __init__(
        self,
        command: Command,
        flags: Flags | None = None,
        *,
        minimum: float | None = None,
        pattern: str = PERCENT_PATTERN,
        reports: str = "",
        tolerance: float = 0.0,
        reason: str = COVERAGE_REASON,
        timeout: float = 600.0,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        on: Sequence[Hook] = (Hook.STOP,),
        name: str = "",
        command_runner: CommandRunner = run_subprocess,
    ) -> None:
        if (flags is None) == (minimum is None):
            raise ValueError(
                "Give `flags` to compare with the session start, or a fixed `minimum`. "
                "Give one of the two."
            )
        self.command = command
        self.flags = flags
        self.minimum = minimum
        self.pattern = re.compile(pattern, re.MULTILINE)
        self.reports = reports
        self.tolerance = tolerance
        self.reason = reason
        self.timeout = timeout
        self.max_output_chars = max_output_chars
        self.on = tuple(on)
        self.name = name
        self.command_runner = command_runner

    @property
    def flag(self) -> str:
        """The flag that holds the baseline. Each gate has a unique label, thus a unique flag."""
        return f"{self.label}-baseline"

    def baseline(self, *, on: Sequence[Hook] = (Hook.SESSION_START,)) -> SetFlag:
        """The process that measures the baseline when the session starts. Add it to the context.

        It keeps the first value of the session, also when `session-start` fires again.
        A failed measurement gives the value None: the gate then has no baseline.
        """
        if self.flags is None:
            raise ValueError(f"'{self.label}' has a fixed minimum. It needs no baseline.")
        return SetFlag(
            self.flags,
            self.flag,
            self.percent,
            on=on,
            keep=True,
            name=self.flag,
        )

    def measure(self, event: HookInput) -> tuple[CommandOutcome, float | None]:
        """Run the command. Return its outcome, and the coverage in percent or None."""
        cwd = working_dir(event)
        if self.reports:
            for stale in cwd.glob(self.reports):
                stale.unlink()
        outcome = self.command_runner(self.command, cwd, self.timeout, event_json(event))
        if self.reports:
            percent = report_coverage(cwd, self.reports)
        else:
            found = list(self.pattern.finditer(outcome.output))
            percent = float(found[-1].group(1)) if found else None
        return outcome, percent

    def percent(self, event: HookInput) -> float | None:
        """Run the command, and return the coverage in percent or None."""
        return self.measure(event)[1]

    def run(self, event: HookInput) -> ProcessResult:
        outcome, percent = self.measure(event)
        floor: Any = self.minimum if self.flags is None else self.flags.get(self.flag)
        origin = "the fixed minimum" if self.flags is None else "the session start"
        shown = display(self.command)
        output = f"Output:\n{tail(outcome.output, self.max_output_chars)}"
        if outcome.exit_code != 0:
            result = block(
                f"`{shown}` failed with exit code {outcome.exit_code}. "
                "Make all tests pass, so that the coverage can be measured. "
                "Do not change or delete tests.",
                output,
            )
        elif percent is None:
            source = f"no report matches '{self.reports}'" if self.reports else "no output matches"
            result = block(
                f"`{shown}` gave no coverage: {source}. Find the cause. "
                "If the coverage setup is broken, tell the user.",
                output,
            )
        elif floor is None:
            result = allow(f"Coverage {percent:.2f} %. No baseline was measured at the start.")
        elif percent + self.tolerance < floor:
            where = f" The reports are '{self.reports}'." if self.reports else ""
            result = block(
                f"The coverage is {percent:.2f} %, below the {floor:.2f} % of {origin}. "
                f"{self.reason}{where}",
                output,
            )
        else:
            result = allow(f"Coverage {percent:.2f} %. The baseline is {floor:.2f} % of {origin}.")
        return result


class PytestCoverage(RequireCoverage):
    """RequireCoverage with pytest-cov, run by the Python interpreter that runs the hook.

    `source` is the package or folder to measure. Without it, the coverage
    configuration of the project selects the files.
    """

    def __init__(self, flags: Flags | None = None, *, source: str = "", **options: Any) -> None:
        command = [
            *PYTEST_COMMAND,
            f"--cov={source}" if source else "--cov",
            "--cov-report=term-missing:skip-covered",
            "--cov-precision=2",
        ]
        options.setdefault("pattern", PYTEST_PATTERN)
        super().__init__(options.pop("command", command), flags, **options)


class DotnetCoverage(RequireCoverage):
    """RequireCoverage with `dotnet test` and coverlet.collector, which .NET test templates have.

    coverlet writes one Cobertura report for each test project into a new subfolder
    of `results`. The gate merges them: a line is covered when one report covers it.
    """

    def __init__(
        self, flags: Flags | None = None, *, results: str = DOTNET_RESULTS, **options: Any
    ) -> None:
        command = [
            "dotnet",
            "test",
            "--nologo",
            "--collect:XPlat Code Coverage",
            "--results-directory",
            results,
        ]
        options.setdefault("reports", f"{results}/**/coverage.cobertura.xml")
        super().__init__(options.pop("command", command), flags, **options)


class TypeScriptCoverage(RequireCoverage):
    """RequireCoverage with Vitest, and its text-summary report of the line coverage.

    For Jest, give `command="npx jest --coverage --coverageReporters=text-summary"`.
    The command is a string because `npx` needs a shell on Windows.
    """

    def __init__(self, flags: Flags | None = None, **options: Any) -> None:
        options.setdefault("pattern", ISTANBUL_PATTERN)
        super().__init__(options.pop("command", VITEST_COMMAND), flags, **options)


def report_coverage(root: Path, pattern: str) -> float | None:
    """The line coverage in percent of the Cobertura or LCOV reports that match a glob.

    Reports of the same file merge: a line is covered when one report covers it.
    None when no report has a line.
    """
    covered: dict[LineKey, bool] = {}
    for report in sorted(root.glob(pattern)):
        for key, hit in _report_lines(report.read_text(encoding="utf-8-sig")):
            covered[key] = covered.get(key, False) or hit
    return 100 * sum(covered.values()) / len(covered) if covered else None


def _report_lines(text: str) -> Iterator[tuple[LineKey, bool]]:
    """Each (file, line) of one report, and whether a test ran it. XML is Cobertura, else LCOV."""
    if text.lstrip().startswith("<"):
        for source in ET.fromstring(text).iter("class"):
            name = source.get("filename", "").replace("\\", "/")
            for line in source.iter("line"):
                yield (name, int(line.get("number", "0"))), int(line.get("hits", "0")) > 0
    else:
        name = ""
        for record in text.splitlines():
            kind, _, value = record.partition(":")
            if kind == "SF":
                name = value.replace("\\", "/")
            elif kind == "DA":
                number, count = value.split(",")[:2]
                yield (name, int(number)), int(count) > 0
