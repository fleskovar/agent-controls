"""The `agent_actions` command line. This module is the composition root."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from agent_actions.app import DEFAULT_TIMEOUT_SECONDS, install_hooks, run_hook
from agent_actions.errors import AgentActionsError
from agent_actions.hcm import BUNDLE_DIR, hcm_init, hcm_update
from agent_actions.model import Harness, Hook
from agent_actions.session import SessionStore

DEFAULT_SKILLS_DEST: Final = Path(".claude/skills")
SKILLS_DIR: Final = BUNDLE_DIR / "skills"
HARNESS_NAMES: Final = tuple(harness.value for harness in Harness)
HOOK_NAMES: Final = tuple(hook.value for hook in Hook)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    # `hcm update` passes the options that it does not know to hcm.
    args, hcm_args = parser.parse_known_args(argv)
    if hcm_args and args.handler is not _hcm_update:
        parser.error(f"unrecognized arguments: {' '.join(hcm_args)}")
    args.hcm_args = hcm_args
    try:
        exit_code = int(args.handler(args))
    except AgentActionsError as error:
        print(f"agent_actions: {error}", file=sys.stderr)
        exit_code = 1
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent_actions", description="Run Python processes on AI agent lifecycle hooks."
    )
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    run = commands.add_parser(
        "run", help="Run a runner file for one hook call. Harnesses call this."
    )
    run.add_argument("runner", type=Path, help="Runner file, relative to the project root.")
    run.add_argument("--harness", required=True, choices=HARNESS_NAMES)
    run.add_argument("--hook", required=True, choices=HOOK_NAMES)
    run.add_argument("--input", type=Path, help="Read the hook payload from this file, not stdin.")
    _add_root(run)
    run.set_defaults(handler=_run)

    install = commands.add_parser("install", help="Write the hook configuration for a runner file.")
    install.add_argument("runner", type=Path, help="Runner file, relative to the project root.")
    install.add_argument("--target", choices=HARNESS_NAMES, help="Harness. Asked when omitted.")
    install.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Hook timeout in seconds."
    )
    _add_root(install)
    install.set_defaults(handler=_install)

    sessions = commands.add_parser("sessions", help="List recorded sessions, newest first.")
    _add_root(sessions)
    sessions.set_defaults(handler=_sessions)

    skills = commands.add_parser("skills", help="Copy the agent skills for authoring processes.")
    skills.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_SKILLS_DEST,
        help=f"Destination folder (default: {DEFAULT_SKILLS_DEST.as_posix()}).",
    )
    skills.set_defaults(handler=_skills)

    hcm = commands.add_parser("hcm", help="Give the agent bundle of this package to hcm.")
    hcm_commands = hcm.add_subparsers(required=True, metavar="HCM_COMMAND")
    init = hcm_commands.add_parser("init", help="Register the agent bundle in the hcm registry.")
    init.add_argument(
        "--dev",
        nargs="?",
        type=Path,
        const=BUNDLE_DIR,
        metavar="PATH",
        help="Development mode: hcm reads the bundle folder in place (default: this package).",
    )
    init.set_defaults(handler=_hcm_init)
    update = hcm_commands.add_parser(
        "update",
        help="Register the bundle of this package version, then update it in this project. "
        "Other options go to `hcm update`, for example: -t claude-code --no-prompt.",
    )
    update.set_defaults(handler=_hcm_update)
    return parser


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(),
        help="Project root that holds .hooks/ (default: current directory).",
    )


def _run(args: argparse.Namespace) -> int:
    payload = (
        args.input.read_text(encoding="utf-8-sig")
        if args.input
        else sys.stdin.buffer.read().decode("utf-8-sig")
    )
    response = run_hook(
        args.root.resolve(), args.runner, Harness(args.harness), Hook(args.hook), payload
    )
    if response.stdout is not None:
        sys.stdout.write(json.dumps(response.stdout) + "\n")
    if response.stderr:
        sys.stderr.write(response.stderr + "\n")
    return response.exit_code


def _install(args: argparse.Namespace) -> int:
    harness = Harness(args.target) if args.target else _ask_harness()
    report = install_hooks(
        args.root.resolve(), args.runner, harness, Path(sys.executable).as_posix(), args.timeout
    )
    print(f"Installed {len(report.hooks)} hook(s) for {harness}: {', '.join(report.hooks)}")
    print(f"Configuration file: {report.config_path}")
    return 0


def _ask_harness() -> Harness:
    if not sys.stdin.isatty():
        raise AgentActionsError(
            f"Give --target. Stdin is not a terminal, so install cannot ask. "
            f"Targets: {', '.join(HARNESS_NAMES)}."
        )
    choices = list(Harness)
    for number, harness in enumerate(choices, start=1):
        print(f"  {number}. {harness}")
    answer = input("Select the harness [1]: ").strip() or "1"
    if not answer.isdigit() or not 1 <= int(answer) <= len(choices):
        raise AgentActionsError(f"'{answer}' is not a number from 1 to {len(choices)}.")
    return choices[int(answer) - 1]


def _sessions(args: argparse.Namespace) -> int:
    summaries = SessionStore(args.root.resolve()).sessions()
    for summary in summaries:
        print(f"{summary.folder}  session={summary.session_id}  agents={', '.join(summary.agents)}")
    if not summaries:
        print("No sessions recorded.")
    return 0


def _skills(args: argparse.Namespace) -> int:
    shutil.copytree(SKILLS_DIR, args.dest, dirs_exist_ok=True)
    copied = sorted(skill.name for skill in SKILLS_DIR.iterdir())
    print(f"Copied {', '.join(copied)} to {args.dest}")
    return 0


def _hcm_init(args: argparse.Namespace) -> int:
    return hcm_init(args.dev)


def _hcm_update(args: argparse.Namespace) -> int:
    return hcm_update(args.hcm_args)
