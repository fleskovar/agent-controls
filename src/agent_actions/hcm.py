"""The `agent_actions hcm` commands: give the agent bundle of this package to hcm.

hcm (harness-config-manager) installs the skills of the bundle into the agent
harnesses of a project. This module runs the `hcm` command. It does not import
hcm, and it does not write the files of the hcm registry.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, cast

from agent_actions.errors import AgentActionsError

BUNDLE_NAME: Final = "agent-actions"
# The bundle is package data, beside this file. After `pip install -e .`, this is
# the folder of the checkout.
BUNDLE_DIR: Final = Path(__file__).resolve().parent / "hcm_bundle"
MANIFEST: Final = "hcm.yaml"
HCM_INSTALL_COMMAND: Final = "npm install -g harness-config-manager"


def find_hcm() -> str:
    """The path of the hcm command. `shutil.which` also finds hcm.cmd on Windows."""
    hcm = shutil.which("hcm")
    if hcm is None:
        raise AgentActionsError(f"hcm is not installed. Install it with: {HCM_INSTALL_COMMAND}")
    return hcm


def hcm_init(dev_path: Path | None = None) -> int:
    """Register the bundle in the hcm registry.

    Without `dev_path`, hcm stores a copy of the bundle of this package. With
    `dev_path`, hcm reads that working copy in place (development mode).
    """
    hcm = find_hcm()
    if dev_path is None:
        exit_code = _register(hcm, BUNDLE_DIR)
        next_step = f"Next: hcm install {BUNDLE_NAME} -t <harness>"
    else:
        # A relative path is read from the current folder.
        bundle = dev_path.resolve()
        if not (bundle / MANIFEST).is_file():
            raise AgentActionsError(
                f"'{bundle}' has no {MANIFEST}. Give the bundle folder: "
                "agent_actions hcm init --dev <path>"
            )
        if "site-packages" in bundle.parts:
            # An installed copy does not change when you edit the working copy.
            print(
                f"agent_actions: '{bundle}' is an installed copy, not a working copy. "
                'Run "pip install -e ." in your checkout, or give the path of the bundle.',
                file=sys.stderr,
            )
        exit_code = _register(hcm, bundle, "--dev")
        next_step = (
            f"Development mode: hcm reads '{bundle}' in place. After each edit, "
            f'run "hcm update {BUNDLE_NAME}" in each test project.'
        )
    if exit_code == 0:
        print(next_step)
    return exit_code


def hcm_update(hcm_args: Sequence[str] = ()) -> int:
    """Register the bundle of this package version, then update it in the current project.

    `hcm_args` go to `hcm update`, for example `-t claude-code --no-prompt`.
    """
    hcm = find_hcm()
    # In development mode, hcm reads the working copy in place. A registration of
    # the installed copy would end that mode.
    exit_code = 0 if _in_development_mode(hcm) else _register(hcm, BUNDLE_DIR)
    if exit_code == 0:
        exit_code = subprocess.run([hcm, "update", BUNDLE_NAME, *hcm_args], check=False).returncode
    return exit_code


def _register(hcm: str, bundle: Path, *options: str) -> int:
    """`hcm registry add` is idempotent: the entry keeps its id, and hcm replaces its copy."""
    return subprocess.run([hcm, "registry", "add", str(bundle), *options], check=False).returncode


def _in_development_mode(hcm: str) -> bool:
    listed = subprocess.run(
        [hcm, "registry", "list", "--json"], capture_output=True, encoding="utf-8", check=False
    )
    entries = (
        cast("list[dict[str, Any]]", json.loads(listed.stdout)) if listed.returncode == 0 else []
    )
    return any(entry.get("name") == BUNDLE_NAME and entry.get("dev") for entry in entries)
