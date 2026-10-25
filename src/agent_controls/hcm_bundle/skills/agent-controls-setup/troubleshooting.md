# Find the cause of a hook problem

## Read the session record

Each hook call writes a record in the project root.

```text
.hooks/flags.json               the flags of the project, as they are now
.hooks/<UTC timestamp>_<short session id>/
    session.json
    flags.json                  the flags of the session, as they are now
    main-agent/
        state.json   the state, the input and the output of each process, for each call
        io.json      the raw stdin, the stdout and the exit code of each call
        log.txt      the aa.log lines, one summary line for each result, one line
                     for each skipped process, and one for each change of the flags
    <agent type>_<timestamp>/   one folder for each subagent
```

List the sessions, newest first:

```bash
python -m agent_controls sessions
```

1. Open `log.txt` of the agent folder. Find the call and the process.
2. Open `io.json`. Find the entry with the same timestamp. Its `stdout` is the
   answer that the harness received.
3. Open `state.json` for the state of the process before and after the call.

If `.hooks/` has no folder for the session, the harness did not call the hook.
See the first rows of the table below.

## Replay one hook call

1. Copy one `stdin` object from `io.json` into a file, for example `payload.json`.
2. Run the call again, without the agent:

   ```bash
   python -m agent_controls run .hooks/agent_checks.py --harness claude --hook pre-tool --input payload.json
   ```

3. Read the standard output, the standard error and the exit code.

Use the harness and the hook of the `io.json` entry. A replay also runs the
commands of the processes, and it writes a new session record.

## Common problems

| Symptom | Cause | Correction |
| --- | --- | --- |
| No hook runs. | The session started before the hooks were registered. | Start a new agent session. |
| No hook runs after a clone or a move of the project. | The hook command has the absolute path of an interpreter that is not there. | Create the virtual environment, then run `agent_controls install` again. |
| A new process does not run. | Its hook is not registered. | Run `agent_controls install` again after each change of the process list. |
| `The runner file ... did not call agent_controls.run(context).` | The last line is missing. | End the runner file with `aa.run(context)`. |
| `Cannot add process ... has no channel for context.` | The hook cannot give context in this harness. | Use a different hook. See [the harness page](./harnesses.md). |
| `Cannot add process ... another process is named ...` | Two processes of one class have no `name`. | Give each process a different `name`. |
| `Give --target. Stdin is not a terminal` | `install` cannot ask for the harness. | Give `--target claude`, `vscode` or `copilot-cli`. |
| A command fails with exit code 127. | The program is not on the PATH of the hook. On Windows, a `.cmd` program such as `npx` does not start from a list command. | Give the full path, or write the command as one string. |
| A command fails with exit code 124. | The command did not finish before the `timeout` of the process. | Increase `timeout` of the process, and `--timeout` of `install`. |
| The harness stops the hook. | The hook timeout is shorter than the commands of that hook. | Run `install` again with a longer `--timeout`. |
| A command with `{paths}` finds no file on Windows. | In a string command, the paths get POSIX quotes. `cmd.exe` does not remove them. | Write the command as a list: `["tool", "{paths}"]`. |
| A formatter does not change the file. | The harness gives absolute paths, and the tool accepts only relative paths. | Use an option of the tool that accepts absolute paths, or check the folder. |
| `RevertWrites` fails on each tool call. | The project is not a git repository, or it has no commit. | Run `git init` and make the first commit, or remove `RevertWrites`. |
| The session records disappear. | `RevertWrites` protects `.hooks/`, and git does not ignore the records. | Add `.hooks/*/` to `.gitignore`. |
| A protected file with work of the user is not reverted. | The file had changes when the session started. | Commit or discard the changes. Then the file is protected again. |
| The agent stops while a check fails. | `Limit` allowed the stop after its maximum of blocked stops. | This is correct. Read the last message of the agent, and review the approach. |
| `BlockReads` blocks a harmless shell command. | The shell check is a substring match. `.env` also matches `.environment`. | Use a longer pattern, or set `check_shell=False`. |
| A process with `when` does not run. | Its condition is false. `log.txt` has a `skipped` line for the process. | Read the flag files. Find in `log.txt` the hook call that changed, or did not change, the flag. |
| A process with `when` never runs, and `log.txt` has no line for it. | The process is in an `if`, or its hook is not registered. | Use `context.add(process, when=...)`, then run `agent_controls install` again. |
| The flags disappear, or `changed_paths` lists `.hooks/flags.json`. | Git does not ignore the flag file. `RevertWrites` deletes it, and a snapshot sees it as a change. | Add `.hooks/flags.json` to `.gitignore`. |
| `A flag of ... is not JSON-serializable` | A process put a value in a flag that is not a JSON type, for example a set. | Use text, numbers, booleans, lists and dicts. |
| A check on the changed files also reads files from before the session. | The session has no baseline. Then each uncommitted change counts. | Start a new session after the install, so that `session-start` saves the snapshot. |
| `git_snapshot` or `changed_paths` fails. | The project is not a git repository, or it has no commit. | Run `git init` and make the first commit. |

## When a process raises an exception

- On a hook that can block, the result is a block. The agent reads the error. A
  broken guardrail does not open the gate.
- On a hook that cannot block, the call exits with code 1 and a message on the
  standard error. The message is also in `log.txt`.

Correct the process. Do not remove it to make the error disappear.
