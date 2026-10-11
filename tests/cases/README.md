# Hook case index

Each folder here is **one behaviour**, written so that a person can read the
inputs, apply the rules in its `README.md`, and arrive at the expected outputs
without running anything. The cases are the readable layer of the suite, on top
of the unit tests in `tests/unit/`; they are also the documentation that turns
the build red when it goes stale.

Run them all, or one, or one under a debugger:

```bash
make test-cases
make test-case  CASE=claude-edit-of-protected-test-is-denied
make debug-case CASE=claude-edit-of-protected-test-is-denied
python tests/cases/case_runner.py claude-edit-of-protected-test-is-denied
```

## The cases

### Path guards: which files the agent may touch

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [claude-edit-of-protected-test-is-denied](claude-edit-of-protected-test-is-denied/) | claude | pre-tool | The main guardrail: an edit of a protected file is denied, and the reason tells the agent what to do. |
| [vscode-edit-outside-protected-paths-gets-no-decision](vscode-edit-outside-protected-paths-gets-no-decision/) | vscode | pre-tool | An allow produces **no** output, so the permission rules of the harness still apply. |
| [copilot-cli-read-of-env-file-is-denied](copilot-cli-read-of-env-file-is-denied/) | copilot-cli | pre-tool | A read of `.env` is denied, with `toolArgs` arriving as a JSON string. |
| [vscode-multi-file-edit-with-one-protected-path-is-denied](vscode-multi-file-edit-with-one-protected-path-is-denied/) | vscode | pre-tool | Path search is recursive: one protected path among several still blocks. |
| [vscode-apply-patch-touching-tests-is-denied](vscode-apply-patch-touching-tests-is-denied/) | vscode | pre-tool | The files of an `apply_patch` call come from the patch headers. |
| [claude-search-of-the-secrets-folder-is-denied](claude-search-of-the-secrets-folder-is-denied/) | claude | pre-tool | A search is a read, and `secrets/**` covers the folder `secrets` itself. |

### Reverts: what git puts back after a tool call

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [claude-shell-change-to-a-protected-test-is-reverted](claude-shell-change-to-a-protected-test-is-reverted/) | claude | post-tool | The main guardrail of `RevertWrites`: a change that a shell command made is reverted, a new file is deleted, and other work stays. |
| [claude-session-start-flags-uncommitted-protected-files](claude-session-start-flags-uncommitted-protected-files/) | claude | session-start | Changes from before the session are flagged to the agent and recorded. Nothing is reverted. |
| [claude-revert-skips-the-files-flagged-at-the-start](claude-revert-skips-the-files-flagged-at-the-start/) | claude | post-tool | A flagged file keeps the work of the user, and it is protected again after it is clean. |
| [copilot-cli-first-tool-call-flags-and-reverts-nothing](copilot-cli-first-tool-call-flags-and-reverts-nothing/) | copilot-cli | post-tool | Without a start hook, the first tool call does the start check, and the limit of that rule. |

### Shell guards: what the agent may run

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [claude-shell-command-rm-rf-is-denied](claude-shell-command-rm-rf-is-denied/) | claude | pre-tool | A blocked expression stops the command, and the reason names the expression that matched. |
| [claude-shell-command-reading-a-secret-is-denied](claude-shell-command-reading-a-secret-is-denied/) | claude | pre-tool | `cat .env` is blocked by the shell heuristic of `BlockReads`, and the limit of that heuristic. |

### Stop hooks: when the agent may finish

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [claude-stop-is-blocked-while-tests-fail](claude-stop-is-blocked-while-tests-fail/) | claude | stop | A failing test command keeps the agent working, with the output as a reason. |
| [loop-guard-allows-the-stop-after-two-blocks](loop-guard-allows-the-stop-after-two-blocks/) | claude | stop | After the recorded limit of blocked stops, the guard releases the stop and resets. |
| [claude-subagent-stop-is-blocked-by-the-linter](claude-subagent-stop-is-blocked-by-the-linter/) | claude | subagent-stop | A stop process on the second hook of its family, under a custom name, blocking a subagent. |

### Feedback and context

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [claude-post-tool-check-gives-lint-output-as-context](claude-post-tool-check-gives-lint-output-as-context/) | claude | post-tool | Lint output after an edit reaches the agent as context, never as a block. |
| [copilot-cli-post-tool-check-uses-additional-context](copilot-cli-post-tool-check-uses-additional-context/) | copilot-cli | post-tool | The **same runner file** as the case above, with the output shape of another harness. |
| [claude-session-start-gives-failing-tests-as-context](claude-session-start-gives-failing-tests-as-context/) | claude | session-start | `RunCommand` with the test command of a C# project: a failed run reaches the agent as context, never as a block. |
| [claude-command-reads-the-hook-event-on-stdin](claude-command-reads-the-hook-event-on-stdin/) | claude | post-tool | The contract for a program in another language: the hook event arrives on stdin as JSON with neutral names. |
| [vscode-prompt-with-a-token-is-blocked](vscode-prompt-with-a-token-is-blocked/) | vscode | user-prompt | A custom process in the runner file, and the VS Code prompt shape (`continue` and `stopReason`). |

### Sessions and state

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [session-folder-collision-adds-one-millisecond](session-folder-collision-adds-one-millisecond/) | claude | session-start | Two sessions with the same short id get two folders, 1 ms apart. |
| [claude-subagent-writes-to-its-own-folder](claude-subagent-writes-to-its-own-folder/) | claude | subagent-stop | A subagent records into its own folder, not into `main-agent`. |
| [tool-call-budget-blocks-after-the-recorded-limit](tool-call-budget-blocks-after-the-recorded-limit/) | claude | pre-tool | State survives between calls, and a blocked call is not counted. |
| [two-guards-combine-to-the-most-restrictive-verdict](two-guards-combine-to-the-most-restrictive-verdict/) | claude | pre-tool | Block beats allow, only the reasons of the winner reach the agent, and both processes record state. |

### Failures that must stay loud

| Case | Harness | Hook | What it pins |
| --- | --- | --- | --- |
| [stop-process-that-asks-fails-loudly](stop-process-that-asks-fails-loudly/) | claude | stop | A verdict the hook cannot deliver fails the run at **run time**, with exit code 1. |
| [context-process-on-a-harness-without-a-channel-is-rejected](context-process-on-a-harness-without-a-channel-is-rejected/) | copilot-cli | session-start | The same protection at **add time**: the harness has no context channel. |
| [a-broken-guardrail-fails-closed](a-broken-guardrail-fails-closed/) | claude | pre-tool | A process that raises becomes a block, with the traceback in the session log. |

### Install

| Case | Harness | What it pins |
| --- | --- | --- |
| [install-claude-keeps-existing-settings](install-claude-keeps-existing-settings/) | claude | Hooks are derived from the runner file, and foreign settings survive. |
| [install-vscode-quotes-an-interpreter-path-with-a-space](install-vscode-quotes-an-interpreter-path-with-a-space/) | vscode | An interpreter path with a space is quoted per shell, in `command` and `windows`. |

## How a case is built

```text
<case-name>/
    inputs/
        case.json      {"harness", "hook", "now"} or {"command": "install", "harness", "python", "timeout"}
        runner.py      the runner file the harness would call
        stdin.json     the hook payload; "{{root}}" becomes the project folder
        commit/        optional files that become the one commit of a git repository in the project
        project/       optional files copied into the project next (a seeded .hooks/ or .claude/,
                       or the uncommitted changes on top of commit/)
    outputs/
        response.json  exit code, stdout document and stderr of the call
        state.json     the newest step of the agent folder: state and outputs per process
        folders.json   every folder under .hooks/, relative and sorted
        worktree.json  the lines of `git status --short` after the call (cases with commit/)
        config.json    the harness configuration file (install cases)
    README.md          behaviour, why it exists, the input rule table, the walkthrough
```

`outputs/` holds only the files the case is **about**, and only those are
compared. A case about folder naming has no `response.json`; a case about a
decision has no `folders.json`.

Everything is deterministic: the clock comes from `case.json`, commands come from
an injected runner inside `inputs/runner.py`, and the case runner puts `{{root}}`
back in place of the temporary folder before it compares.

A case with `inputs/commit/` runs on a real git repository, because git is the
unit that `RevertWrites` reads. The case runner builds the repository from the
two input folders: `commit/` and the runner file are the last commit, and
`project/` is the work tree on top of it. A file that occurs in both folders is a
modified file. A file only in `project/` is a new file.

## Adding a case

1. Copy the closest folder and rename it after the behaviour, not the code.
2. Write `inputs/` first, then compute `outputs/` **by hand** from the rules, then
   run it. Never paste what the code printed without checking every value.
3. Write the walkthrough in `README.md` as numbered steps a reader can follow
   with the rules in `docs/`. One behaviour per folder.
4. Add a row to the table above.
5. Break the rule on purpose, watch this case go red, restore it. A case that
   cannot fail proves nothing.

`make bless-case CASE=<name>` rewrites the baselines. Read every changed line
before you commit it: a red case is a regression or a requirement change, and the
second one needs a new case rather than an overwritten one.
