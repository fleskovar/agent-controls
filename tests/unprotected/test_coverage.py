"""The coverage gate: no stop while the coverage is below the session start or a fixed minimum."""

import re
import sys
from pathlib import Path
from typing import Any

import pytest
from builders import an_event

from agent_actions.app import install_hooks, run_hook
from agent_actions.harnesses import make_adapter
from agent_actions.model import Harness, Hook, Verdict
from agent_actions.processes import (
    CommandOutcome,
    DotnetCoverage,
    PytestCoverage,
    RequireCoverage,
    TypeScriptCoverage,
    report_coverage,
)
from agent_actions.processes.commands import Command
from agent_actions.runtime import compatibility_problems

START = an_event(Hook.SESSION_START)
STOP = an_event(Hook.STOP)


def runner(*outputs: str, exit_code: int = 0) -> Any:
    """A command runner that gives the outputs in order."""
    queue = list(outputs)

    def run(command: Command, cwd: Path, timeout: float, stdin: str) -> CommandOutcome:
        return CommandOutcome(exit_code, queue.pop(0))

    return run


def test_drop_below_the_session_start_blocks_and_equal_coverage_passes() -> None:
    flags: dict[str, Any] = {}
    gate = RequireCoverage(
        "cov", flags, command_runner=runner("total 80.5 %", "total 80.4 %", "total 80.5 %")
    )

    gate.baseline().run(START)

    assert flags == {"RequireCoverage-baseline": 80.5}
    dropped = gate.run(STOP)
    assert dropped.verdict is Verdict.BLOCK
    assert "80.40 %, below the 80.50 % of the session start" in dropped.reasons[0]
    assert gate.run(STOP).verdict is Verdict.ALLOW


def test_baseline_keeps_the_first_value_when_session_start_fires_again() -> None:
    flags: dict[str, Any] = {}
    gate = RequireCoverage("cov", flags, command_runner=runner("70%", "90%"))
    baseline = gate.baseline()

    baseline.run(START)
    baseline.run(START)

    assert flags[gate.flag] == 70.0


def test_fixed_minimum_needs_no_baseline_and_tolerance_allows_a_small_drop() -> None:
    gate = RequireCoverage(
        "cov", minimum=90, tolerance=0.5, command_runner=runner("89.6%", "89.4%")
    )

    assert gate.run(STOP).verdict is Verdict.ALLOW
    assert "of the fixed minimum" in gate.run(STOP).reasons[0]
    with pytest.raises(ValueError, match="fixed minimum"):
        gate.baseline()


@pytest.mark.parametrize("arguments", [{}, {"flags": {}, "minimum": 90}])
def test_gate_needs_exactly_one_of_flags_and_minimum(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="Give one of the two"):
        RequireCoverage("cov", **arguments)


def test_failing_command_or_missing_number_blocks_and_missing_baseline_allows() -> None:
    failing = RequireCoverage("cov", minimum=0, command_runner=runner("1 failed", exit_code=1))
    silent = RequireCoverage("cov", minimum=0, command_runner=runner("no number"))
    no_baseline = RequireCoverage(
        "cov", {"RequireCoverage-baseline": None}, command_runner=runner("5%")
    )

    assert "failed with exit code 1" in failing.run(STOP).reasons[0]
    assert "gave no coverage: no output matches" in silent.run(STOP).reasons[0]
    assert no_baseline.run(STOP).verdict is Verdict.ALLOW


COBERTURA = """<?xml version="1.0"?><coverage><packages><package><classes>
<class filename="src\\Pricing.cs"><lines>
<line number="1" hits="%s"/><line number="2" hits="0"/>
</lines></class></classes></package></packages></coverage>"""


def test_reports_of_one_file_merge_and_stale_reports_are_deleted(tmp_path: Path) -> None:
    for folder, hits in [("a", "1"), ("b", "0")]:
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "coverage.cobertura.xml").write_text(COBERTURA % hits, "utf-8")
    (tmp_path / "lcov.info").write_text("SF:src/a.ts\nDA:1,3\nDA:2,0\nDA:3,0,abc\nend_of_record\n")

    assert report_coverage(tmp_path, "**/coverage.cobertura.xml") == 50.0
    assert report_coverage(tmp_path, "lcov.info") == pytest.approx(100 / 3)
    assert report_coverage(tmp_path, "none/*.xml") is None

    # The command writes no report: the old ones are gone, so the gate cannot pass on them.
    gate = DotnetCoverage(minimum=0, results="a", command_runner=runner(""))
    result = gate.run(an_event(Hook.STOP, root=str(tmp_path)))
    assert "no report matches 'a/**/coverage.cobertura.xml'" in result.reasons[0]
    assert not (tmp_path / "a" / "coverage.cobertura.xml").exists()


def test_each_variant_reads_the_output_format_of_its_tool() -> None:
    pytest_output = "src/a.py   10   1  90.00%   7\n------\nTOTAL      20   2  87.25%\n"
    vitest_output = "Statements   : 50% ( 1/2 )\nLines        : 85.71% ( 6/7 )\n"
    python, typescript = PytestCoverage(minimum=0), TypeScriptCoverage(minimum=0)

    assert re.findall(python.pattern, pytest_output) == ["87.25"]
    assert re.findall(typescript.pattern, vitest_output) == ["85.71"]
    assert "--cov=pkg" in PytestCoverage(minimum=0, source="pkg").command
    assert DotnetCoverage(minimum=0).reports == ".hooks/coverage/**/coverage.cobertura.xml"


@pytest.mark.parametrize("harness", list(Harness))
def test_gate_and_baseline_work_in_each_harness(harness: Harness) -> None:
    gate = PytestCoverage({})
    adapter = make_adapter(harness)

    assert compatibility_problems(gate, adapter) == []
    assert compatibility_problems(gate.baseline(), adapter) == []


RUNNER = f"""
import sys
import agent_actions as aa
from agent_actions.processes import RequireCoverage

context = aa.get_current_context()
gate = RequireCoverage([{sys.executable!r}, "-c", "print(open('cov.txt').read() + '%')"],
                       context.session_flags, name="coverage")
context.add(gate.baseline())
context.add(gate)
aa.run(context)
"""


def test_the_baseline_of_the_session_start_reaches_the_stop_through_the_session_flags(
    tmp_path: Path,
) -> None:
    (tmp_path / "checks.py").write_text(RUNNER, encoding="utf-8")

    def call(hook: Hook) -> dict[str, Any] | None:
        response = run_hook(
            tmp_path, Path("checks.py"), Harness.CLAUDE, hook, '{"session_id": "s"}'
        )
        assert response.exit_code == 0, response.stderr
        return None if response.stdout is None else dict(response.stdout)

    assert install_hooks(tmp_path, Path("checks.py"), Harness.CLAUDE, "python").hooks == (
        Hook.SESSION_START,
        Hook.STOP,
    )
    (tmp_path / "cov.txt").write_text("80")
    call(Hook.SESSION_START)
    (tmp_path / "cov.txt").write_text("79.9")
    blocked = call(Hook.STOP)
    assert blocked is not None and blocked["decision"] == "block"
    assert "79.90 %, below the 80.00 %" in blocked["reason"]
    (tmp_path / "cov.txt").write_text("81")
    assert call(Hook.STOP) is None
