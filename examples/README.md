# Examples: flags, conditions and snapshots

Each file in this folder is a complete runner file. Each one uses the three
features that let a guardrail react to the context, not only to one hook call:

- **Flags.** `context.flags` is state for all sessions of the project.
  `context.session_flags` is state for one session.
- **Conditions.** `context.add(process, when=...)` runs a process only when a
  function of the hook event returns a true value.
- **Snapshots.** `git_snapshot` saves the state of the work tree in a flag.
  `changed_paths` gives the files that changed after it.

[docs/processes.md](../docs/processes.md#flags-and-conditions) is the reference.

## The examples

| File | Behaviour | Flags | Git |
| --- | --- | --- | --- |
| [checks_on_changed_files.py](checks_on_changed_files.py) | The linter reads only the files that the session changed. The tests run only after a change of a source file. | session: `baseline` | yes |
| [tests_due_across_sessions.py](tests_due_across_sessions.py) | A session that ends while the tests fail leaves a debt. The next session gets a note, and cannot stop before the tests pass. | project: `tests-due` | no |
| [read_before_write.py](read_before_write.py) | The agent cannot change `src/` before it reads the architecture guide. | session: `guide-read` | no |
| [change_budget_per_prompt.py](change_budget_per_prompt.py) | When one prompt changed 10 files, the harness asks the user before the next write. | session: `turn` | yes |
| [paired_changes.py](paired_changes.py) | A change of the API needs a change of the documentation. A change of the dependencies needs a changelog entry. | session: `baseline` | yes |
| [exit_strategies.py](exit_strategies.py) | After 5 failed stops in a row, the agent can stop and ask for help. The next session gets a review note. After 2 denied writes to `migrations/`, the user decides. | project: `needs-review` | no |
| [human_switches.py](human_switches.py) | A person edits `.hooks/flags.json` to freeze the source code, or to give each session a note. | project: `freeze`, `note` | no |

An example with "yes" in the Git column needs a git repository with one commit
or more.

## Try an example

1. Copy the file into your project, for example as `agent_checks.py`.
2. Change the patterns and the commands at the top of the file.
3. Register the hooks:

   ```bash
   agent_controls install agent_checks.py --target claude
   ```

4. Start the agent, and give it a task that the docstring of the file describes.
5. Read the result:

   | File | Content |
   | --- | --- |
   | `.hooks/flags.json` | The project flags. |
   | `.hooks/<session>/flags.json` | The session flags. |
   | `.hooks/<session>/main-agent/log.txt` | Each result, each skipped process, and each changed flag. |

To combine two examples, put their `context.add` lines in one runner file. Call
`aa.run(context)` one time, at the end. Give each process a different name.

## The patterns behind the examples

**One hook sets, a later hook reads.** `read_before_write.py` sets a flag after a
read, and a guard on a later write reads it. Any event can open or close a
guard: a tool call, a prompt, the stop of a subagent.

**A snapshot is a baseline, and you select its lifetime.** A snapshot at
`session-start` with `keep=True` gives the changes of the session. A snapshot at
each `user-prompt` gives the changes of one turn. A snapshot in `context.flags`
gives the changes after a moment in an earlier session.

**A condition keeps a slow check out of the calls that do not need it.**
`change_budget_per_prompt.py` reads git only before a write tool.

**The runner file runs again at each hook call.** The flags are loaded before
it. Thus the value of a flag can be a part of a reason or of a context, as in
`human_switches.py`.

**Use `when`, not `if`.** `install` loads the runner file with empty flags. A
process in an `if` on a flag is not added, and its hook is not registered.

## More ideas

These are not in the folder. Each one needs 10 to 30 lines.

- **Review before the stop.** `SetFlag(session, "reviewed", on=[Hook.SUBAGENT_STOP])`
  with `when=lambda event: event.agent_type == "code-reviewer"`. A stop process
  blocks the main agent while source files changed and the flag is not set.
- **Handover between sessions.** At each stop, a process saves
  `changed_paths(...)` in a project flag. At the next session start, `AddContext`
  gives that list to the new agent.
- **Last green state.** A command runner saves `git_snapshot` in a project flag
  when the tests pass. Each later session then knows the files that changed
  after the tests last passed.
- **Strikes.** A process counts the blocked writes on protected files in a
  project flag. After 3, each session starts with a warning, or each write
  needs the approval of the user.
- **Modes from the prompt.** A prompt that contains `#careful` sets a session
  flag. With that flag, `ToolCallBudget` and a stricter `BlockShellCommands` run.
- **A slow check one time for each day.** A project flag holds the date of the
  last full security scan. The scan runs only when the date is not the date of
  today.
- **A baseline for each subagent.** `SetFlag` on `subagent-start` saves a
  snapshot under the name of the agent type. The stop of that subagent then
  checks only its own files.

## Limits

- A flag is a file. An agent that can write in `.hooks/` can change it.
  `human_switches.py` shows the protection.
- When two parallel hook calls change the same flag, the last call wins.
- `tests_due_across_sessions.py` and `human_switches.py` add context on
  `session-start`. Copilot CLI has no context channel there. Remove that process
  for Copilot CLI.

`tests/unprotected/test_examples.py` loads each example and runs its behaviour
through real hook calls.
