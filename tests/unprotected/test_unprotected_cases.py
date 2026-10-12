"""Runs the hook case folders that the user moved here from tests/protected/cases/.

An agent can change the tests in this folder. Refer to `protected` in
.hooks/agent_checks.yaml.
"""

from pathlib import Path

from case_runner import case_dirs, read_baselines, run_case


def test_each_unprotected_hook_case_matches_its_baseline(tmp_path: Path) -> None:
    for case_dir in case_dirs(Path(__file__).parent):
        expected = read_baselines(case_dir)
        assert expected, f"{case_dir.name} has no outputs/*.json"

        actual = run_case(case_dir, tmp_path / case_dir.name)

        for name, document in expected.items():
            assert actual[name] == document, f"{case_dir.name}/outputs/{name}"
