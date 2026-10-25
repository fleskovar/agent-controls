# Julia

Template: `./assets/julia_checks.py`. It also needs `./assets/coverage_floor.py`
beside the runner file.

## The checks

| Moment | Name | Command | Purpose |
| --- | --- | --- | --- |
| Start | `tests-at-start` | `julia --project -e "using Pkg; Pkg.test()"` | Show the tests that fail already. |
| After an edit of `*.jl` | `format` | `julia -e "using JuliaFormatter; format(ARGS)" {paths}` | Format the edited file. |
| Stop | `format-check` | `julia -e "using JuliaFormatter; exit(format(ARGS; overwrite=false) ? 0 : 1)" src test` | Fail when a file is not formatted. |
| Stop | `tests-and-coverage` | `coverage_floor.py 80 .hooks/coverage/lcov.info -- julia --project -e "<tests with coverage>"` | Fail on a failing test, and below the coverage floor. |

## Before you start

- The project root must be a package: a `Project.toml`, `src/` and
  `test/runtests.jl`.
- Install the two tools into the default environment of Julia. The commands load
  them from there, and the project does not get them as dependencies:

  ```bash
  julia -e "using Pkg; Pkg.add(ARGS)" JuliaFormatter Coverage
  ```

- Add `*.cov` to `.gitignore`. A test run with coverage writes these files
  beside the source files.
- Commit a `.JuliaFormatter.toml`, so that the agent and the editor use one style.

## Things to know

- Each `julia` command starts a new process and loads its packages. That costs
  some seconds. The format step after an edit is the slowest part of the
  template. Delete it if the delay is too long, and keep the `format-check` on
  the stop.
- `Pkg.test(coverage=true)` writes one `.cov` file for each source file and each
  process. `Coverage.process_folder("src")` merges them, and
  `LCOV.writefile` writes the report that `coverage_floor.py` reads. The command
  deletes the `.cov` files before and after the test run.
- The floor is for the files in `src`. Change the two `"src"` texts in
  `TESTS_WITH_COVERAGE` to measure a different folder.
- Julia has no separate linter. Put static checks into the test suite, and the
  `tests-and-coverage` gate runs them:

  ```julia
  using Aqua, JET
  Aqua.test_all(MyPackage)
  JET.test_package(MyPackage; target_defined_modules = true)
  ```

- A full test run after each edit is slow, because of the compile time. The
  template has none. To add one for a small package:

  ```python
  context.add(CheckAfterEdit(TESTS, patterns=SOURCE_FILES, name="tests-after-edit"))
  ```

- The tests with coverage are slower than the tests without it. The process has a
  timeout of 900 seconds. Give `--timeout 1200` to `agent_controls install`.

## Typical protected paths

```python
PROTECTED: dict[str, list[str]] = {
    "Only a person changes these tests. Fix the code, not the test.": ["test/protected/**"],
    "These files set the dependencies and the checks. Ask the user to change them.": [
        "Project.toml",
        "Manifest.toml",
        ".JuliaFormatter.toml",
        ".hooks/*.py",
    ],
}
```
