from pathlib import Path

import pytest
from case_runner import case_dirs, read_baselines, run_case

CASES = case_dirs()


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_hook_case_matches_its_baseline(case_dir: Path, tmp_path: Path) -> None:
    expected = read_baselines(case_dir)
    assert expected, f"{case_dir.name} has no outputs/*.json"

    actual = run_case(case_dir, tmp_path / "project")

    for name, document in expected.items():
        assert actual[name] == document, f"{case_dir.name}/outputs/{name}"


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_hook_case_has_a_readme(case_dir: Path) -> None:
    assert (case_dir / "README.md").is_file()
