# Other languages

Agent Controls runs each program. A language needs no adapter. Find one command
for each row of this table, then put the commands into the closest template.

| Row | Question | Process |
| --- | --- | --- |
| Tests | Which command runs all tests, and exits with a code other than 0 on a failure? | `RequireCommand` on the stop, `RunCommand` at the start |
| Fast feedback | Which command checks an edit in less than 10 seconds? | `CheckAfterEdit` |
| Format | Which command formats the files that it gets as arguments? | `CheckAfterEdit` with `{paths}` |
| Lint and types | Which command fails on a lint, type or build problem? | `RequireCommand` on the stop |
| Coverage | Does the test output show the percentage? If not, can the tool write Cobertura or LCOV? | `RequireCoverage` with `pattern` or `reports` |

## Procedure

1. Read the CI file and the build script of the project. Use their commands.
2. Run each command by hand in the project root. Read the exit code: `echo $?`,
   or `echo %ERRORLEVEL%` in `cmd.exe`.
3. Make sure that a failing test gives an exit code other than 0. Some tools
   need an option for that.
4. Copy `./assets/csharp_checks.py` to `.hooks/agent_checks.py`. Replace its
   commands and its file patterns.
5. Continue with the procedure of [the skill](./SKILL.md), from the coverage step.

## Commands of common toolchains

Make sure that each command is correct for the version of the tool in the project.

| Toolchain | After an edit | Stop: lint and types | Stop: tests | Coverage |
| --- | --- | --- | --- | --- |
| TypeScript | `npx prettier --write {paths}` | `npx tsc --noEmit`, `npx eslint .` | `npx vitest run` | `TypeScriptCoverage(flags)` |
| Go | `gofmt -w {paths}` | `go vet ./...` | `go test ./...` | No option. Use a script that reads the `total:` line of `go tool cover -func=cover.out` |
| Rust | `rustfmt {paths}` | `cargo clippy --all-targets -- -D warnings` | `cargo test` | `cargo llvm-cov --fail-under-lines 80` |
| C and C++ with CMake | `clang-format -i {paths}` | `cmake --build build` with warnings as errors | `ctest --test-dir build --output-on-failure` | `gcovr --fail-under-line 80` |

On Windows, `npx` is a `.cmd` file. Write an `npx` command as one string, and do
not use `{paths}` in it. Check the folder instead: `"npx prettier --check src"`.

## A check in your own program

To decide in a script, in any language:

1. Read the hook event from the standard input, as one JSON object. Its keys are
   `harness`, `hook`, `session_id`, `cwd`, `root`, `agent_id`, `agent_type`,
   `tool`, `prompt`, `last_message` and `stop_hook_active`. `tool` has `name`,
   `kind`, `arguments`, `paths`, `command` and `output`.
2. Print the message for the agent.
3. Exit with code 0 for a pass, or with a different code for a failure.

Then add the script with `RequireCommand`, `CheckAfterEdit` or `RunCommand`.
