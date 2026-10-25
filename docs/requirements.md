# Agent Controls: refined requirements

Status: baseline, 2026-09-15. Source: [task.md](../task.md).

This document states what the framework must do. It replaces the informal
specification in `task.md` where the two disagree. Section 4 lists each
refinement and the reason for it.

## 1. Purpose

Agent Controls is a Python SDK and a CLI. With it, a project writes Python code
that runs when an AI agent harness fires a lifecycle hook. The framework gives
that code:

- one data model for hook inputs and results, for all supported harnesses,
- state that persists between hook calls in the same session,
- a record of every hook call, for debugging and for tests,
- a set of ready-to-use guardrails.

## 2. Terms

| Term | Meaning |
| --- | --- |
| Harness | The program that runs the agent and fires hooks: Claude Code, VS Code (GitHub Copilot agent), GitHub Copilot CLI. |
| Hook | A neutral lifecycle point, for example `pre-tool` or `stop`. Each harness has its own name for it. |
| Process | A Python class that runs on one or more hooks and returns a `ProcessResult`. |
| Runner file | A Python file that creates processes, adds them to the context and calls `agent_controls.run(context)`. |
| Session | One agent conversation. The harness gives it an id. |
| Agent folder | The folder that holds the files of the main agent or of one subagent in a session. |
| Verdict | The decision of a process: `allow`, `block` or `ask`. |
| Reasons | Text that tells the agent why a process blocked, asked or allowed. |
| Context | Text that the framework adds to the agent context, when the hook has a channel for it. |
| Flag | A named JSON value that processes share, for one session or for all sessions of the project. |
| Condition | A function of the hook event. It decides whether a process runs on a hook call. |

## 3. Functional requirements

### 3.1 Harnesses

- **R1.** The framework supports the harnesses `claude`, `vscode` and `copilot-cli`.
- **R2.** One adapter module per harness contains all harness-specific
  knowledge: event names, input field names, output format, configuration file,
  tool names. A factory function selects the adapter from the harness name.
- **R3.** To add a harness, a developer adds one adapter module and one factory
  entry. No other module changes.

### 3.2 Hooks

- **R4.** The neutral hooks are `session-start`, `user-prompt`, `pre-tool`,
  `post-tool`, `stop`, `subagent-start`, `subagent-stop`, `pre-compact` and
  `session-end`.
- **R5.** Each adapter declares the hooks that its harness supports, and for
  each hook the verdicts and the context channel that the harness can deliver.
  [data-model.md](data-model.md) contains the full table.

### 3.3 Processes

- **R6.** A process extends one process family. The family fixes the hooks that
  the process can attach to:

  | Family | Hooks |
  | --- | --- |
  | `PreToolProcess` | `pre-tool` |
  | `PostToolProcess` | `post-tool` |
  | `PromptProcess` | `user-prompt` |
  | `StopProcess` | `stop`, `subagent-stop` |
  | `StartProcess` | `session-start`, `subagent-start` |
  | `EventProcess` | any hook; verdict `allow` only |

- **R7.** A process sets `on` to a subset of its family hooks. The default is
  the first family hook.
- **R8.** `context.add(process)` rejects a process when one of its hooks is not
  in its family, or when the target harness does not support that hook. The
  error occurs during `install` and during `run`.
- **R9.** During `run`, the framework executes only the processes whose `on`
  contains the current hook.
- **R10.** Two processes in one context must not have the same name. The
  default name is the class name. A process sets `name` to change it.

### 3.4 Results

- **R11.** A process returns `ProcessResult(verdict, reasons, context)`. The
  helpers `allow()`, `block()` and `ask()` create results.
- **R12.** A `block` or `ask` result must have at least one reason.
- **R13.** When more than one process runs, the most restrictive verdict wins:
  `block` before `ask` before `allow`. The reasons of a `block` or `ask`
  verdict go to the agent, each with the process name as a prefix. The context
  of all processes goes to the agent. Reasons of `allow` results go to
  `log.txt` only, so that the agent does not get noise on each tool call.
- **R14.** An `allow` result on `pre-tool` never approves a tool call. The
  harness permission rules continue to apply.
- **R15.** When the harness cannot deliver a verdict or a context, the run
  fails with exit code 1 and a message on stderr. The failure is never silent.
  `Context.add` also rejects a process when its declared verdicts or its
  context use cannot reach the agent on one of its hooks.
- **R16.** When a process raises an exception, the framework writes the
  traceback to `log.txt`. If the hook can block, the result is `block` with the
  error as the reason (fail closed). Otherwise the run fails with exit code 1.

### 3.5 State

- **R17.** A process declares state variables as attributes that its
  `__state__` method sets. The framework calls `__state__` to get the initial
  values and the variable names.
- **R18.** Before a process runs, the framework loads the most recent recorded
  state of that process from the agent folder, if one exists. Unknown recorded
  variables are ignored. Missing variables keep their initial value.
- **R19.** After a process runs, the framework records its state, its input and
  its output under a new timestamp in `state.json`.
- **R20.** State values must be JSON-serializable. Otherwise the run fails with
  a message that names the process and the variable.

### 3.6 Session files

- **R21.** The framework writes all session files under `.hooks/` in the
  project root. The project root is the current working directory of the CLI.
- **R22.** Layout:

  ```text
  .hooks/
      flags.json
      <timestamp>_<short-session-id>/
          session.json
          flags.json
          main-agent/
              state.json  io.json  log.txt
          <agent-type>_<timestamp>/
              agent.json
              state.json  io.json  log.txt
  ```

- **R23.** A timestamp is UTC in the form `YYYYMMDDTHHMMSSmmm`, for example
  `20260915T232455123`. String sort gives chronological order.
- **R24.** The short session id is the first 8 characters of the session id
  after the removal of characters other than letters, digits and `-`.
- **R25.** When a new folder name exists already for a different session or
  agent, the framework adds 1 ms to the timestamp until the name is free.
- **R26.** `session.json` and `agent.json` contain the full ids. The framework
  uses them to find the folder of a known session or agent.
- **R27.** `io.json` records, per timestamp: harness, hook, raw stdin payload,
  stdout payload and exit code.
- **R28.** `agent_controls.log(message)` appends a line to `log.txt` of the
  current agent folder. The line contains the timestamp and the process name.
- **R29.** The framework holds a lock file on the agent folder while it loads,
  runs and records a step. Parallel hook calls for one agent do not lose state.

### 3.7 CLI

- **R30.** `agent_controls run RUNNER --harness H --hook K [--input FILE]` reads
  the hook payload from stdin (or FILE), executes the runner file, writes the
  harness response to stdout and exits with the harness exit code.
- **R31.** `agent_controls install RUNNER [--target H] [--timeout S]` finds the
  hooks that the runner file uses and writes or merges the configuration file
  of the harness. Entries from other tools stay unchanged. The command in the
  configuration uses the absolute path of the Python interpreter that runs
  `install`, so a virtual environment works.
- **R32.** When `--target` is missing and stdin is a terminal, `install` asks
  the user to select the harness. When stdin is not a terminal, `install` fails.
- **R33.** `agent_controls sessions` lists the recorded sessions, newest first.
- **R34.** `agent_controls skills [--dest DIR]` copies the agent skills of the
  package into a project.
- **R47.** `agent_controls hcm init` registers the agent bundle of the package in
  the hcm registry. `agent_controls hcm update` registers the bundle of the
  installed package version, then updates it in the current project. Both run
  the `hcm` command, and both fail with its install command when it is missing.

### 3.8 Included processes

- **R35.** `BlockWrites(patterns)` blocks write tools on matching paths.
- **R36.** `BlockReads(patterns)` blocks read, search and write tools on
  matching paths.
- **R37.** Both path guards also block shell commands that contain a protected
  path. This check is a heuristic.
- **R38.** `BlockShellCommands(patterns)` blocks shell commands that match a
  regular expression.
- **R39.** `RequireCommand(command)` runs a command on `stop` and blocks the
  stop while the command fails. `RequireTests` is `RequireCommand` with
  `pytest -q` as the default.
- **R40.** Deprecated by R59. `LoopGuard(process, max_blocks)` wraps a stop process. After
  `max_blocks` consecutive blocks it allows the stop and tells the agent to
  report that the strategy needs a review.
- **R41.** `CheckAfterEdit(command)` runs a command on `post-tool` after a write
  tool and gives the failure output to the agent.
- **R42.** `AddContext(text)` adds text to the agent context on start hooks and
  on `user-prompt`.
- **R43.** `ToolCallBudget(max_calls)` blocks tool calls after a maximum number
  of calls per agent.
- **R44.** `RevertWrites(patterns)` runs on `post-tool`. It uses git to find
  changes to matching paths, reverts them, and tells the agent that the files
  are protected. On the start hooks, it tells the agent to ask the user about
  matching paths that already have uncommitted changes, and it does not revert
  those paths.
- **R45.** `RunCommand(command)` runs a command on any hook that has a context
  channel, and gives the failure output to the agent as context.
- **R46.** Each command process writes the hook event as JSON to the standard
  input of its command. The exit code and the output are the answer of the
  command.

### 3.9 Flags and conditions

- **R48.** A flag is a named JSON value. Project flags are in `.hooks/flags.json`,
  and all sessions share them. Session flags are in `flags.json` in the session
  folder, and the agents of that session share them.
- **R49.** The framework loads the flags before the runner file. The runner
  file gets them as the dicts `context.flags` and `context.session_flags`.
- **R50.** After a hook call, the framework writes only the flags that the call
  changed. A parallel call that changed a different flag loses nothing.
- **R51.** A flag value that is not JSON-serializable fails the run with exit
  code 1, and the flag file stays unchanged.
- **R52.** `context.add(process, when=condition)` gives a process a condition.
  The process runs only when the condition returns a true value for the event.
- **R53.** The framework evaluates a condition immediately before its process,
  in the order of the processes. `install` evaluates no condition, so the hook
  of each process is registered.
- **R54.** A process that does not run has no record in `state.json`, and
  `log.txt` has a line for it. A condition that raises is handled as in R16.
- **R55.** `log.txt` names each flag that a hook call changed.
- **R56.** `SetFlag(flags, flag, value)` sets a flag on the hooks in `on`. The
  value can be a function of the event. With `keep`, it does not replace a value.
- **R57.** `git_snapshot` records the state of the git work tree.
  `changed_paths` returns the paths whose content changed after a snapshot.
  Without a snapshot, it returns each uncommitted change.
- **R58.** `on_changed_paths` gives a command only the files that changed after
  a snapshot, and passes when there are none. `clear_on_pass` deletes a flag
  when a command passes.

### 3.10 Limits

- **R59.** `Limit(process, max_in_a_row, max_total)` wraps a process of any
  family, and counts the results that `counts` selects (default: each block).
  A result that is not counted resets the count in a row. The total never resets.
- **R60.** The result that reaches a maximum gets `message`. Each counted result
  after a maximum gets the verdict `then`: allow, ask or block. A release resets
  the count in a row. With `flags` and `flag`, a release sets the flag.
- **R61.** `Limit` has the hooks, the family and the verdicts of the wrapped
  process, plus `then`. Thus `Context.add` rejects a `then` verdict that a hook
  cannot deliver (R15).
- **R62.** `Process.needs(hook)` gives the verdicts and the context use of a
  process on one hook. `Context.add` and the engine check these. The default is
  `verdicts` and `uses_context` on each hook.
- **R63.** On each hook in `reset_on`, `Limit` resets the count in a row. On a
  `reset_on` hook that the wrapped process does not use, `Limit` only allows.
- **R64.** With `problem`, a counted result with a new problem name starts the
  count in a row again. With `window`, `max_total` applies to the counted
  results of the last `window` seconds.
- **R65.** With `store`, `Limit` keeps its counts in that flags dict, under its
  name. The agents and the sessions that share the dict share the counts.

## 4. Refinements to task.md

| task.md | Refined | Reason |
| --- | --- | --- |
| `__state__` is abstract. | `__state__` is optional. | Most guardrails have no state. |
| `load_state()` and `persist_state()` do I/O. | `load_state(saved)` and `dump_state()` are pure. The session store does the I/O. | Processes stay testable without files. |
| One `AbstractProcess`. | Process families per hook group (R6). | A family makes an incompatible attachment an error, not a silent failure. |
| `run(context_input)`. | `run(event: HookInput)`. | The input is one typed object for all harnesses. |
| `aa.getCurrentContext()`. | `get_current_context()`, with `getCurrentContext` as an alias. | Python naming, but the task example still works. |
| Harness event names in runner files. | Neutral hook names. | Runner files stay harness-agnostic. |
| The hook command contains only the runner file. | The command also contains `--harness` and `--hook`. | Copilot CLI payloads do not contain the event name. |
| "reasons" is optional on all results. | `block` and `ask` require a reason (R12). | A block without a reason gives the agent no way to recover. |
| `allow` returns a decision to the harness. | `allow` on `pre-tool` outputs no decision (R14). | An explicit allow bypasses the harness permission prompt. |
| State per session. | State per agent folder. | Subagents have their own loop counters. |
| Files: `state.json`, `log.txt`, `io.json`. | Also `session.json` and `agent.json` (R26). | Trimmed folder names are not unique ids. |

## 5. Non-functional requirements

- **N1.** The runtime has one third-party dependency, GitPython. Only
  `RevertWrites` and the snapshot functions (R57) import it. All other code uses
  the Python 3.11+ standard library only.
- **N2.** The framework works on Windows, Linux and macOS.
- **N3.** A runner file that contains only path guards completes a `pre-tool`
  call in less than 300 ms on a developer machine.
- **N4.** All harness-specific data is in the adapter modules (R2).

## 6. Out of scope

- HTTP, prompt and MCP hook types. The framework generates `command` hooks only.
- Events without a neutral hook: `PermissionRequest`, `Notification`,
  `errorOccurred` and similar.
- Changes to tool input (`updatedInput`, `modifiedArgs`).
- An `uninstall` command. Remove the entries from the configuration file.
- Clean-up of old session folders.

## 7. Known limitations

- VS Code also loads `.claude/settings.json` and `.github/hooks/*.json`.
  Copilot CLI also loads `.claude/settings.json`. If you install for more than
  one harness in one project, a harness can run the hooks of another harness.
  Install for one harness per project.
- The harness documentation changes often. The tool name lists in the adapters
  are the names that the documentation gave on 2026-09-15.
- The shell command check in the path guards is a substring match. A command
  that builds a path at run time is not detected.
- A flag is a file under `.hooks/`. An agent that can write there can change a
  flag. When two parallel hook calls change the same flag, the last call wins.
