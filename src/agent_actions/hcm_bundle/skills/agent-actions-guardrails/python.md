# Python

Template: `./assets/python_checks.py`. The test tool has a coverage threshold, so
`coverage_floor.py` is not necessary.

## The checks

| Moment | Name | Command | Purpose |
| --- | --- | --- | --- |
| After an edit of `*.py` | `format` | `python -m ruff format {paths}` | Format the edited file. |
| After an edit of `*.py` | `affected-tests` | `python -m pytest --testmon -q` | Run only the tests that the edit affects. |
| Stop | `lint` | `python -m ruff check src tests` | Fail on a lint problem. |
| Stop | `types` | `python -m mypy` | Fail on a type error. |
| Stop | `tests-and-coverage` | `python -m pytest -q --cov=<package> --cov-fail-under=80` | Fail on a failing test, and below the coverage floor. |

`python` is `sys.executable`: the interpreter that runs the hook.

## Before you start

- Install agent_actions into the virtual environment of the project. Install the
  tools there too:

  ```bash
  python -m pip install ruff mypy pytest pytest-cov pytest-testmon
  ```

- Set `COVERAGE_PACKAGE` to the import name of the package, and `LINT_PATHS` to
  the folders of the code.
- Put the options of ruff, mypy and pytest in `pyproject.toml`. Add that file to
  `PROTECTED`.

## Things to know

- `pytest --testmon` records which tests run which lines. After an edit, it runs
  only the affected tests. The first run is a full run. Add `.testmondata*` to
  `.gitignore`.
- pytest-testmon needs the C tracer of coverage. The template sets
  `COVERAGE_CORE=ctrace`. Without it, on Python 3.14, testmon skips tests that an
  edit affects.
- The affected tests give early feedback, so the template runs no tests at the
  session start. To add that, use `RunCommand` as the other templates do.
- For pyright, replace the `types` command with `[PYTHON, "-m", "pyright"]`.
- `ruff check` and `ruff format --check` accept file paths. To read only the files
  that the session changed, use pattern 1 of
  [Checks that depend on the context](./flags-and-conditions.md).
- `RequireTests()` is a short form of `RequireCommand` with `python -m pytest -q`.
  Use `RequireCommand` when the command needs options.

## Typical protected paths

```python
PROTECTED: dict[str, list[str]] = {
    "Only a person changes these tests. Fix the code, not the test.": ["tests/protected/**"],
    "These files set the dependencies and the checks. Ask the user to change them.": [
        "pyproject.toml",
        ".hooks/*.py",
    ],
}
```
