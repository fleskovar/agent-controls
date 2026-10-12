"""The use cases behind the CLI: run one hook call, and install a runner file."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from agent_actions.engine import ProcessRecord, execute
from agent_actions.errors import AgentActionsError, PayloadError, RunnerFileError
from agent_actions.harnesses import make_adapter
from agent_actions.harnesses.base import HarnessAdapter
from agent_actions.model import Harness, Hook, HookInput, Response
from agent_actions.runtime import load_runner
from agent_actions.session import LOCK_FILE, SessionStore
from agent_actions.storage import file_lock, read_json, write_json

Clock = Callable[[], datetime]

DEFAULT_TIMEOUT_SECONDS: Final = 300
RUN_MODULE_ARGS: Final = ("-m", "agent_actions", "run")


def system_clock() -> datetime:
    return datetime.now(UTC)


def parse_payload(text: str) -> dict[str, Any]:
    """The hook payload as a JSON object. Empty input is an empty object."""
    try:
        payload: Any = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as error:
        raise PayloadError(f"The hook payload is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise PayloadError("The hook payload must be a JSON object.")
    return cast("dict[str, Any]", payload)


def run_hook(
    root: Path,
    runner: Path,
    harness: Harness,
    hook: Hook,
    payload_text: str,
    clock: Clock = system_clock,
) -> Response:
    """Run the processes of a runner file for one hook call, and record the step."""
    adapter = make_adapter(harness)
    response: Response
    if hook not in adapter.capabilities:
        response = _failure(f"Harness '{harness}' has no '{hook}' hook.")
    else:
        try:
            payload = parse_payload(payload_text)
        except PayloadError as error:
            response = _failure(str(error))
        else:
            runner_path = runner if runner.is_absolute() else root / runner
            response = _run_recorded(root, runner_path, adapter, hook, payload, clock)
    return response


def _run_recorded(
    root: Path,
    runner: Path,
    adapter: HarnessAdapter,
    hook: Hook,
    payload: Mapping[str, Any],
    clock: Clock,
) -> Response:
    event = replace(adapter.parse(hook, payload), root=str(root))
    store = SessionStore(root)
    agent_dir = store.agent_dir(event, clock())
    records: tuple[ProcessRecord, ...] = ()
    lines: tuple[str, ...] = ()
    with file_lock(agent_dir / LOCK_FILE):
        try:
            project, session = store.flag_files(agent_dir)
            context = load_runner(runner, adapter, hook, event, project.flags, session.flags)
            step = execute(
                context.active(), event, adapter.capabilities[hook], store.saved_states(agent_dir)
            )
            changed = {"project": project.save(), "session": session.save()}
        except AgentActionsError as error:
            response = _failure(str(error))
            records, lines = (), (f"[agent_actions] ERROR: {error}",)
        else:
            response = Response(stdout=adapter.render(hook, step.result))
            records = step.records
            lines = step.log_lines + tuple(
                f"[agent_actions] changed {scope} flags: {', '.join(names)}"
                for scope, names in changed.items()
                if names
            )
        store.record(agent_dir, clock(), records, _io_record(event, payload, response), lines)
    return response


def _failure(message: str) -> Response:
    return Response(exit_code=1, stderr=f"agent_actions: {message}")


def _io_record(event: HookInput, payload: Mapping[str, Any], response: Response) -> dict[str, Any]:
    return {
        "harness": event.harness,
        "hook": event.hook,
        "stdin": dict(payload),
        "stdout": None if response.stdout is None else dict(response.stdout),
        "exit_code": response.exit_code,
        "stderr": response.stderr,
    }


@dataclass(frozen=True, slots=True)
class InstallReport:
    config_path: Path
    hooks: tuple[Hook, ...]


def install_hooks(
    root: Path,
    runner: Path,
    harness: Harness,
    python: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> InstallReport:
    """Write the hook configuration of a harness for the hooks that a runner file uses."""
    adapter = make_adapter(harness)
    runner_path = runner if runner.is_absolute() else root / runner
    hooks = load_runner(runner_path, adapter, None, None).hooks()
    if not hooks:
        raise RunnerFileError(f"The runner file '{runner}' adds no processes. Nothing to install.")
    runner_arg = relative_posix(runner_path, root)
    commands = {
        hook: (
            python,
            *RUN_MODULE_ARGS,
            runner_arg,
            "--harness",
            harness.value,
            "--hook",
            hook.value,
        )
        for hook in hooks
    }
    config_path = root / adapter.config_path
    document = adapter.merge_config(read_json(config_path), commands, runner_arg, timeout)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(config_path, document)
    return InstallReport(config_path, hooks)


def relative_posix(path: Path, root: Path) -> str:
    """The path relative to the root with '/' separators, or absolute when outside the root."""
    resolved = path.resolve()
    try:
        text = resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        text = resolved.as_posix()
    return text
