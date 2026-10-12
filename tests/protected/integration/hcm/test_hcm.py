"""The hcm bundle of the package, and the `agent_actions hcm` commands.

The tests that run hcm use a temporary HCM_HOME and the project scope only. Thus
they change neither the hcm registry nor the home folders of the user.
"""

import json
import re
import runpy
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent_actions import processes
from agent_actions.cli import main
from agent_actions.harnesses import make_adapter
from agent_actions.hcm import BUNDLE_DIR, BUNDLE_NAME, HCM_INSTALL_COMMAND
from agent_actions.model import Harness, Hook
from agent_actions.process import Process
from agent_actions.runtime import load_runner

REPO = next(
    folder for folder in Path(__file__).resolve().parents if (folder / "pyproject.toml").is_file()
)
SKILLS = BUNDLE_DIR / "skills"
ASSETS = SKILLS / "agent-actions-guardrails" / "assets"
TEMPLATES = sorted(ASSETS.glob("*_checks.py"))
EMPTY_TABLE = "PROTECTED: dict[str, list[str]] = {"
HCM = shutil.which("hcm") or "hcm"
INSTALL_OPTIONS = ["-t", "claude-code", "--no-prompt"]
needs_hcm = pytest.mark.skipif(shutil.which("hcm") is None, reason="hcm is not installed")


def package_version() -> str:
    return str(tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))["project"]["version"])


# --- the bundle ---------------------------------------------------------------------


def test_the_bundle_has_the_version_of_the_package() -> None:
    manifest = (BUNDLE_DIR / "hcm.yaml").read_text(encoding="utf-8")

    assert re.search(rf"^version: {re.escape(package_version())}$", manifest, re.MULTILINE)


def test_the_reference_describes_each_included_process() -> None:
    reference = (SKILLS / "agent-actions-processes" / "reference.md").read_text(encoding="utf-8")
    included = [
        name
        for name in processes.__all__
        if isinstance(getattr(processes, name), type)
        and issubclass(getattr(processes, name), Process)
    ]

    assert [name for name in included if f"\n## {name}\n" not in reference] == []


@pytest.mark.parametrize("harness", list(Harness))
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.stem)
def test_each_runner_template_loads_in_each_harness(
    template: Path, harness: Harness, tmp_path: Path
) -> None:
    text = template.read_text(encoding="utf-8")
    assert EMPTY_TABLE in text
    runner = tmp_path / "agent_checks.py"
    # One protected group, so that the path guards of the template load too.
    runner.write_text(
        text.replace(EMPTY_TABLE, EMPTY_TABLE + '"Fix the code.": ["tests/protected/**"],', 1),
        encoding="utf-8",
    )

    hooks = load_runner(runner, make_adapter(harness), None, None).hooks()

    assert {Hook.PRE_TOOL, Hook.POST_TOOL, Hook.STOP} <= set(hooks)


def test_a_template_without_protected_paths_adds_no_path_guard() -> None:
    [template] = [path for path in TEMPLATES if path.stem == "csharp_checks"]

    hooks = load_runner(template, make_adapter(Harness.CLAUDE), None, None).hooks()

    assert hooks == (Hook.SESSION_START, Hook.POST_TOOL, Hook.STOP)


# --- coverage_floor.py --------------------------------------------------------------

COBERTURA = """<?xml version="1.0" encoding="utf-8"?>
<coverage><packages><package><classes>
  <class filename="src\\Fees.cs"><lines>
    <line number="1" hits="{first}"/><line number="2" hits="{second}"/>
  </lines></class>
</classes></package></packages></coverage>
"""
LCOV = "SF:src/fees.jl\nDA:3,1\nDA:4,0\nLH:1\nLF:2\nend_of_record\n"


@pytest.fixture
def coverage_floor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The `main` function of the script, with the temporary folder as the working folder."""
    monkeypatch.chdir(tmp_path)
    return runpy.run_path(str(ASSETS / "coverage_floor.py"))["main"]


def test_cobertura_reports_of_one_file_merge(coverage_floor: Any, tmp_path: Path) -> None:
    for name, first, second in (("a", 1, 0), ("b", 0, 2)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "coverage.cobertura.xml").write_text(
            "﻿" + COBERTURA.format(first=first, second=second), encoding="utf-8"
        )

    assert coverage_floor(["100", "**/coverage.cobertura.xml"]) == 0
    assert coverage_floor(["100", "a/*.xml"]) == 1


def test_lcov_below_the_floor_fails_and_names_the_lines(
    coverage_floor: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "lcov.info").write_text(LCOV, encoding="utf-8")

    assert coverage_floor(["50", "lcov.info"]) == 0
    assert coverage_floor(["80", "lcov.info"]) == 1
    assert "src/fees.jl: 4" in capsys.readouterr().out


def test_a_failing_command_wins_and_an_old_report_does_not_pass(
    coverage_floor: Any, tmp_path: Path
) -> None:
    report = tmp_path / "lcov.info"
    report.write_text("SF:a\nDA:1,1\n", encoding="utf-8")
    fail = [sys.executable, "-c", "raise SystemExit(3)"]
    write_nothing = [sys.executable, "-c", "pass"]

    assert coverage_floor(["80", "lcov.info", "--", *fail]) == 3
    assert not report.exists()
    assert coverage_floor(["80", "lcov.info", "--", *write_nothing]) == 1
    assert coverage_floor(["80"]) == 2


# --- agent_actions hcm ---------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project as the working folder, and an empty hcm registry."""
    monkeypatch.setenv("HCM_HOME", str(tmp_path / "hcm-home"))
    folder = tmp_path / "project"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


def hcm(*arguments: str) -> str:
    completed = subprocess.run(
        [HCM, *arguments], capture_output=True, encoding="utf-8", timeout=120, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def registry_entry() -> dict[str, Any]:
    [entry] = [
        item
        for item in json.loads(hcm("registry", "list", "--json"))
        if item["name"] == BUNDLE_NAME
    ]
    return entry


@needs_hcm
def test_hcm_accepts_the_bundle() -> None:
    hcm("validate", str(BUNDLE_DIR))
    hcm("refs", "check", "--path", str(BUNDLE_DIR))


@needs_hcm
def test_init_registers_the_bundle_and_update_keeps_its_entry(project: Path) -> None:
    assert main(["hcm", "init"]) == 0
    first = registry_entry()
    hcm("install", BUNDLE_NAME, *INSTALL_OPTIONS)

    assert main(["hcm", "update", *INSTALL_OPTIONS]) == 0

    assert (first["version"], first.get("dev", False)) == (package_version(), False)
    assert registry_entry()["id"] == first["id"]
    assert (project / ".claude/skills/agent-actions-setup/SKILL.md").is_file()
    assert (project / ".claude/skills/agent-actions-guardrails/assets/coverage_floor.py").is_file()
    assert "## Agent Actions" in (project / "CLAUDE.md").read_text(encoding="utf-8")


@needs_hcm
def test_update_installs_the_edits_of_a_development_bundle(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["hcm", "init"]) == 0
    released = registry_entry()
    working_copy = project.parent / "site-packages" / "hcm_bundle"
    shutil.copytree(BUNDLE_DIR, working_copy)

    assert main(["hcm", "init", "--dev", str(working_copy)]) == 0
    hcm("install", BUNDLE_NAME, *INSTALL_OPTIONS)
    page = Path("skills/agent-actions-setup/harnesses.md")
    with (working_copy / page).open("a", encoding="utf-8") as file:
        file.write("\nAn edit of the working copy.\n")
    assert main(["hcm", "update", *INSTALL_OPTIONS]) == 0

    entry = registry_entry()
    assert (entry["id"], entry["dev"]) == (released["id"], True)
    assert "An edit of the working copy." in (project / ".claude" / page).read_text("utf-8")
    assert "is an installed copy, not a working copy" in capsys.readouterr().err


@needs_hcm
def test_init_dev_rejects_a_folder_without_a_manifest(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["hcm", "init", "--dev", str(project)]) == 1
    assert "has no hcm.yaml" in capsys.readouterr().err


def test_without_hcm_the_commands_give_its_install_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "")

    assert (main(["hcm", "init"]), main(["hcm", "update"])) == (1, 1)
    assert HCM_INSTALL_COMMAND in capsys.readouterr().err


def test_only_hcm_update_accepts_options_that_the_parser_does_not_know() -> None:
    with pytest.raises(SystemExit):
        main(["sessions", "--no-prompt"])
