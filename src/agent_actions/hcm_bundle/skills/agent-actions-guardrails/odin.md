# Odin

Template: `./assets/odin_checks.py`.

## The checks

| Moment | Name | Command | Purpose |
| --- | --- | --- | --- |
| Start | `tests-at-start` | `odin test tests -all-packages <vet flags>` | Show the tests that fail already. |
| After an edit of `*.odin` | `check` | `odin check . <vet flags>` | Type check and vet rules, without code generation. |
| Stop | `vet` | `odin check . <vet flags>` | The same check as a gate. |
| Stop | `tests` | `odin test tests -all-packages <vet flags> -define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true` | Fail on a failing test, a memory leak or a bad free. |

The vet flags of the template are `-vet -strict-style -vet-tabs -disallow-do
-warnings-as-errors`.

## Before you start

- Set `PACKAGE` to the folder that `odin check` reads, and `TEST_PACKAGES` to the
  folder of the tests. If the tests are beside the source, use the source folder
  for both.
- Use the vet flags of the build script and the CI of the project in `VET`. The
  agent then gets the same result as a person.
- If the package is a library without a `main` procedure, add `-no-entry-point`
  to `CHECK`.
- If the project needs a collection, add it to `CHECK` and `TESTS`, for example
  `-collection:shared=shared`.

## Things to know

- The compiler has no linter. The vet flags are the linter: unused code, unused
  imports, shadowing and style. Thus `odin check` is the lint step.
- The compiler has no formatter. `odinfmt` comes with the `ols` language server.
  If the project commits an `odinfmt.json`, add a format step. Make sure that the
  options are correct for the `odinfmt` version of the project:

  ```python
  context.add(CheckAfterEdit(["odinfmt", "-w", "{paths}"], patterns=SOURCE_FILES, name="format"))
  ```

- The test runner tracks memory by default. It reports a leak, and the test still
  passes. `-define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true` makes a leak and a bad free
  a failure. A guardrail needs the failure.
- To run one test by hand, add `-define:ODIN_TEST_NAMES=package.procedure_name`.
- `odin check` is fast, so the template runs it after each edit. `odin test`
  compiles the tests. Add it after an edit only when the test run is fast:

  ```python
  context.add(CheckAfterEdit(TESTS, patterns=SOURCE_FILES, name="tests-after-edit"))
  ```

- Do not let the agent make a check pass with a removed vet flag, a `#+vet`
  file tag or `-vet-packages`. Add the build script to `PROTECTED`.

## A coverage floor

Odin has no coverage tool. An external tool can measure a test executable that
has debug information, and write a Cobertura report. `./assets/coverage_floor.py`
reads that report.

1. Build the test executable with `-debug`. Add the options to the `tests`
   process, so that it builds and runs the tests:

   ```python
   TEST_BINARY = ".hooks/coverage/tests.exe"  # no ".exe" on Linux and macOS
   TESTS = [*TESTS, "-debug", "-build-mode:exe", f"-out:{TEST_BINARY}"]
   ```

2. After the `tests` process, add a process that runs the executable in the
   coverage tool. The processes of one hook run in the order of the runner file.

   On Linux, with `kcov`:

   ```python
   SOURCE = str(Path("src").resolve())
   context.add(
       Limit(
           RequireCommand(
               [
                   sys.executable,
                   ".hooks/coverage_floor.py",
                   "80",
                   ".hooks/coverage/kcov/**/cobertura.xml",
                   "--",
                   "kcov",
                   f"--include-path={SOURCE}",
                   ".hooks/coverage/kcov",
                   TEST_BINARY,
               ],
               reason="Add tests for the lines without coverage. Do not change or delete tests.",
               name="coverage",
           ),
           max_in_a_row=3,
       )
   )
   ```

   On Windows, with `OpenCppCoverage`:

   ```python
   [
       sys.executable,
       ".hooks/coverage_floor.py",
       "80",
       ".hooks/coverage/coverage.xml",
       "--",
       "OpenCppCoverage",
       "--sources",
       SOURCE,
       "--export_type",
       "cobertura:.hooks/coverage/coverage.xml",
       "--",
       TEST_BINARY,
   ]
   ```

3. Run the command by hand. Make sure that the report lists the source files of
   the project, and not the files of the Odin `core` collection.
4. Measure the coverage, then set the floor.

## Typical protected paths

```python
PROTECTED: dict[str, list[str]] = {
    "Only a person changes these tests. Fix the code, not the test.": ["tests/protected/**"],
    "These files set the build and the checks. Ask the user to change them.": [
        "build.bat",
        "build.sh",
        "Makefile",
        "odinfmt.json",
        ".hooks/*.py",
    ],
    "Vendored code does not change. Wrap it in your own package.": ["vendor/**"],
}
```
