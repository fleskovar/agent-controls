"""Fail when the line coverage in Cobertura or LCOV reports is below a floor.

    python coverage_floor.py MINIMUM REPORT_GLOB [-- COMMAND ...]

MINIMUM is a percentage. REPORT_GLOB is relative to the working folder, and `**`
matches folders at any depth. With a command, the script first deletes the
reports that match, then runs the command. When the command fails, the script
stops with its exit code. Thus an old report never passes for a new test run.

Reports of the same file merge: a line is covered when one report covers it.

Exit codes: 0 at or above the floor, 1 below it or without coverage data, 2 for
wrong arguments, or the exit code of the command.

This script uses the standard library only. Copy it next to the runner file.
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

OPTION_COUNT = 2  # MINIMUM and REPORT_GLOB
USAGE_EXIT_CODE = 2
SHOWN_FILES = 10
SHOWN_LINES = 20

Hits = dict[tuple[str, int], int]


def add_report(hits: Hits, text: str) -> None:
    """Merge the hits of each (file, line) of one report. XML is Cobertura. Other text is LCOV."""
    if text.lstrip().startswith("<"):
        for source in ET.fromstring(text).iter("class"):
            for line in source.iter("line"):
                _add(
                    hits, source.get("filename", ""), line.get("number", "0"), line.get("hits", "0")
                )
    else:
        name = ""
        for record in text.splitlines():
            kind, _, value = record.partition(":")
            if kind == "SF":
                name = value
            elif kind == "DA":
                number, count = value.split(",")[:2]
                _add(hits, name, number, count)


def _add(hits: Hits, name: str, number: str, count: str) -> None:
    key = (name.replace("\\", "/"), int(number))
    hits[key] = max(hits.get(key, 0), int(count))


def check(minimum: float, pattern: str) -> int:
    """Print the line coverage of the reports that match. Return 1 when it is below the minimum."""
    hits: Hits = {}
    for report in sorted(Path().glob(pattern)):
        add_report(hits, report.read_text(encoding="utf-8-sig"))
    if not hits:
        print(f"No coverage data: no report with lines matches '{pattern}'.")
        return 1
    covered = sum(count > 0 for count in hits.values())
    percent = 100 * covered / len(hits)
    print(f"Line coverage: {percent:.1f} % ({covered} of {len(hits)} lines). Floor: {minimum:g} %.")
    if percent < minimum:
        missed: dict[str, list[str]] = {}
        for (name, number), count in sorted(hits.items()):
            if count == 0:
                missed.setdefault(name, []).append(str(number))
        print("Lines without coverage, the file with the most lines first:")
        for name, numbers in sorted(missed.items(), key=lambda item: -len(item[1]))[:SHOWN_FILES]:
            more = " ..." if len(numbers) > SHOWN_LINES else ""
            print(f"  {name}: {', '.join(numbers[:SHOWN_LINES])}{more}")
    return int(percent < minimum)


def main(argv: Sequence[str]) -> int:
    split = argv.index("--") if "--" in argv else len(argv)
    options, command = argv[:split], argv[split + 1 :]
    if len(options) != OPTION_COUNT:
        print(__doc__, file=sys.stderr)
        return USAGE_EXIT_CODE
    minimum, pattern = float(options[0]), options[1]
    exit_code = 0
    if command:
        for stale in Path().glob(pattern):
            stale.unlink()
        # One stream for the command: the coverage result is then the last text that
        # the caller reads, also when the command writes to the standard error.
        exit_code = subprocess.run(command, stderr=subprocess.STDOUT, check=False).returncode
    return exit_code or check(minimum, pattern)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
