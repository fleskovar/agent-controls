# Add a harness

A harness is one adapter module plus one line in the factory. No other module
changes. Plan half a day, most of it reading the hook documentation of the new
harness.

## 1. Collect the facts

Answer these questions from the documentation of the harness, and write the
answers into the module docstring with the date you read them:

1. Which lifecycle events exist, and what are their exact names?
2. Which of them map to a neutral `Hook`? Leave out the ones that do not.
3. What does stdin hold per event? Field names and their case.
4. What does the harness read from stdout per event? Which decisions are honored?
5. Which decisions does it **ignore**? That answer becomes the capability table.
6. What are the tool names, and which argument holds a path or a command?
7. Where does the configuration file live, and what is its shape?
8. Which shell runs the hook command on Windows?

If the documentation does not answer question 5, assume the narrow answer. A
capability that is too wide turns into silence in the agent, which is the failure
this framework exists to remove.

## 2. Write the adapter

Copy `src/agent_actions/harnesses/copilot_cli.py`, which is the most independent
of the three. Implement the `HarnessAdapter` protocol from `harnesses/base.py`:

```python
class MyHarnessAdapter:
    harness = Harness.MY_HARNESS
    tools = TOOLS                 # a ToolCatalog
    capabilities = CAPABILITIES   # Mapping[Hook, Capability]
    config_path = PurePosixPath(".myharness/hooks.json")

    def parse(self, hook: Hook, payload: Mapping[str, Any]) -> HookInput: ...
    def render(self, hook: Hook, result: ProcessResult) -> Mapping[str, Any] | None: ...
    def merge_config(self, existing, commands, runner, timeout) -> dict[str, Any]: ...
```

Use the shared helpers, and do not repeat them:

| Helper | Purpose |
| --- | --- |
| `ToolCatalog.call(name, arguments, output)` | Builds the `ToolCall`: kind, paths and command. |
| `find_paths(value, keys)` | Every path at any depth, for tools that edit several files. |
| `as_mapping`, `as_text`, `optional_text` | Payload values that arrive in more than one shape. |
| `reason_text`, `context_text` | The joining rules for reasons and context. |
| `command_line(argv, shell)` | Shell-safe quoting. Unquoted when nothing needs quoting. |
| `is_own_command(command, runner)` | Finds the entries of an earlier install of the same runner file. |
| `parse_snake_case`, `render_claude_style` (in `claude.py`) | Reuse these when the harness follows the Claude Code format. |

Rules that keep the adapter correct:

- **Never widen a capability to make a process fit.** The table states what the
  harness does, not what you want it to do.
- **Render nothing for an `allow`.** An explicit approval switches off the
  permission prompt of the user.
- **Keep `merge_config` additive.** Remove only the entries of the same runner
  file, and copy every other key of the document.
- **Put the harness names in module constants**, so a documentation change is a
  one-line edit.

## 3. Register it

```python
# src/agent_actions/model.py
class Harness(StrEnum):
    ...
    MY_HARNESS = "my-harness"

# src/agent_actions/harnesses/__init__.py
_ADAPTERS: Final[Mapping[Harness, HarnessAdapter]] = {
    ...
    Harness.MY_HARNESS: MyHarnessAdapter(),
}
```

The CLI reads the harness names from the enum, so `--harness` and `--target`
accept the new value at once.

## 4. Test it

Copy the folder `tests/protected/unit/harnesses/copilot_cli_adapter/`, change the name
of the folder and of its test file, and cover four things:

1. **parse**: one payload per interesting shape. Assert the tool kind, the paths
   and the identity fields.
2. **render**: parametrized over hook and verdict, with the expected document.
   Include `allow`, which must render `None`.
3. **capabilities**: assert the hooks the harness lacks, so a later copy and
   paste cannot add them by accident.
4. **merge_config**: one existing foreign entry, one entry of the same runner
   file. Assert that the foreign entry survives and the own entry is replaced.

Then add one case folder under `tests/protected/cases/` that runs a real guardrail end to
end in the new harness. `copilot-cli-read-of-env-file-is-denied` is the template.

## 5. Check it against the real harness

Unit tests prove the adapter matches your reading of the documentation, not that
your reading is right. Before you call the harness supported:

1. Install a runner file with `BlockWrites(["tests/**"])` in a scratch project.
2. Ask the agent to edit a file under `tests/`.
3. Confirm that the agent reports the block, and that it states your reason.
4. Look at `.hooks/<session>/main-agent/io.json` and compare the recorded stdin
   with the fields your `parse` reads.
5. Repeat for a stop hook, which is the one that harnesses implement most
   differently.

If step 3 shows the edit going through, the harness ignored your output. The
capability table or the render shape is wrong, and no test will tell you.

## 6. Document it

- Add the rows for the new harness to [data-model.md](data-model.md): hook names,
  capabilities, input fields, output shapes, tool catalog, configuration file.
- Add the configuration file to the table in `README.md`.
- Add a line to the known limitations in [requirements.md](requirements.md) if
  the harness reads the configuration files of another harness.
