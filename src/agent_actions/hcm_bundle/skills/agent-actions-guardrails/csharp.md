# C# and .NET

Template: `./assets/csharp_checks.py`. It also needs `./assets/coverage_floor.py`
beside the runner file.

## The checks

| Moment | Name | Command | Purpose |
| --- | --- | --- | --- |
| Start | `tests-at-start` | `dotnet test --nologo` | Show the tests that fail already. |
| After an edit of `*.cs` | `format` | `dotnet format whitespace --folder --include {paths}` | Format the edited file. |
| Stop | `format-check` | `dotnet format --verify-no-changes` | Fail on a style or analyzer problem that has a fix. |
| Stop | `build` | `dotnet build --nologo -warnaserror` | Fail on each compiler and analyzer warning. |
| Stop | `tests-and-coverage` | `coverage_floor.py 80 <reports> -- dotnet test --collect:"XPlat Code Coverage"` | Fail on a failing test, and below the coverage floor. |

## Before you start

- The commands run in the project root. Put one solution file there. If the
  root has more than one, add the solution path after `dotnet format`, `dotnet
  build` and `dotnet test` in the template.
- Each test project needs the `coverlet.collector` package. The xUnit, NUnit and
  MSTest templates of .NET include it.
- Put the analyzer and style rules in `.editorconfig` and
  `Directory.Build.props`. `dotnet format` and the build read them. Add the two
  files to `PROTECTED`.

## Things to know

- `dotnet format --include` accepts only paths relative to the solution folder.
  With an absolute path, it formats nothing and exits with code 0. The harness
  gives absolute paths. Thus the template uses `dotnet format whitespace
  --folder`, which accepts them. That command corrects whitespace only.
- `dotnet format --verify-no-changes` exits with code 2 when a file needs a
  change. It also runs the style rules and the analyzers that have a severity of
  `warning` or more.
- coverlet writes one `coverage.cobertura.xml` for each test project, each in a
  new folder with a random name. `coverage_floor.py` deletes the old reports
  before the test run, and merges the new reports. A line is covered when one
  test project covers it.
- A test run after each edit is slow in .NET. The template has none. To add one
  for a small solution, use a filter that selects fast tests:

  ```python
  context.add(
      CheckAfterEdit([*TESTS, "--filter", "Category=Unit"], patterns=SOURCE_FILES, name="unit-tests")
  )
  ```

- The first command after a change restores and builds. Give `--timeout 1200` to
  `agent_actions install` for a large solution.

## A coverage floor without the script

With the `coverlet.msbuild` package in each test project, the test command has a
threshold option. Then `coverage_floor.py` is not necessary:

```python
RequireCommand(
    [*TESTS, "-p:CollectCoverage=true", "-p:Threshold=80", "-p:ThresholdType=line"],
    name="tests-and-coverage",
)
```

With more than one test project, coverlet applies this threshold to each project
separately. Use the script when the floor is for the merged coverage.

## Typical protected paths

```python
PROTECTED: dict[str, list[str]] = {
    "Only a person changes these tests. Fix the code, not the test.": ["tests/Protected/**"],
    "These files set the build and the analyzers. Ask the user to change them.": [
        "Directory.Build.props",
        "Directory.Packages.props",
        ".editorconfig",
        ".hooks/*.py",
    ],
    "Migrations that ran in production do not change. Add a new migration.": ["**/Migrations/**"],
}
```
