"""`make publish`, `make version-minor`, `make version-major`.

    python scripts/release.py publish        bump the patch, commit, tag, push
    python scripts/release.py bump minor     start the next minor (or major)

A release is a pushed v* tag: .github/workflows/publish.yml tests, builds and
uploads it to PyPI. So `publish` does not upload anything itself. It writes the
tag that the workflow waits for and pushes it with the commit that names the
same version.

The patch number belongs to the machine; the major and minor belong to a
person. So `publish` bumps the patch only when the version in pyproject.toml is
already released: its tag exists, or PyPI already has it. A version with no
release was set by `bump` to start a new minor or major. `publish` releases
that version as it is, so 0.2.0 goes out and 0.2.1 comes next.

Stdlib only, so it runs without the venv.
"""

from __future__ import annotations

import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE_BRANCH = "main"
WORKFLOW = "publish.yml"
PACKAGE = "agent-controls"

# Every file that carries the package version, with the pattern of its version
# line. The bundle version is the package version (tests/protected/integration/hcm/test_hcm.py).
VERSION_FILES = {
    "pyproject.toml": re.compile(r'^(version = ")([^"]+)(")', re.MULTILINE),
    "src/agent_controls/hcm_bundle/hcm.yaml": re.compile(r"^(version: )(\S+)()", re.MULTILINE),
}


def fail(message: str) -> None:
    print(f"release: {message}", file=sys.stderr)
    sys.exit(1)


def run(*args: str, check: bool = True, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=quiet, check=False)
    if check and result.returncode != 0:
        fail(f"{' '.join(args)} failed" + (f":\n{result.stderr.strip()}" if quiet else ""))
    return result


def git(*args: str) -> str:
    return run("git", *args).stdout.strip()


def tag_exists(version: str) -> bool:
    return run("git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}", check=False).returncode == 0


def on_pypi(version: str) -> bool:
    url = f"https://pypi.org/pypi/{PACKAGE}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=15):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        fail(f"PyPI answered {exc.code} for {url}")
    except urllib.error.URLError as exc:
        fail(f"cannot reach PyPI to check {version}: {exc.reason}")
    return False


def read_version(root: Path = ROOT) -> str:
    path, pattern = next(iter(VERSION_FILES.items()))
    match = pattern.search((root / path).read_text(encoding="utf-8"))
    if not match:
        fail(f"no version line in {path}")
    return match.group(2)  # type: ignore[union-attr]


def write_version(version: str, root: Path = ROOT) -> None:
    for path, pattern in VERSION_FILES.items():
        file = root / path
        text, count = pattern.subn(rf"\g<1>{version}\g<3>", file.read_text(encoding="utf-8"), count=1)
        if count != 1:
            fail(f"no version line in {path}")
        file.write_text(text, encoding="utf-8", newline="")


def next_version(version: str, part: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        fail(f"version {version} is not MAJOR.MINOR.PATCH")
    major, minor, patch = map(int, match.groups())  # type: ignore[union-attr]
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def commit_version(version: str, message: str) -> None:
    write_version(version)
    files = list(VERSION_FILES)
    run("git", "add", "--", *files)
    run("git", "commit", "-q", "-m", message, "--", *files)


def require_clean() -> None:
    if git("status", "--porcelain"):
        fail("the working tree has uncommitted changes. Commit or stash them first.")


def repo_url(remote: str) -> str | None:
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", git("remote", "get-url", remote))
    return f"https://github.com/{match.group(1)}" if match else None


def publish() -> None:
    require_clean()
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != RELEASE_BRANCH:
        fail(f"releases are made from {RELEASE_BRANCH}, and this is {branch}.")
    upstream = run("git", "rev-parse", "--abbrev-ref", "@{u}", check=False)
    if upstream.returncode != 0:
        fail(f"{branch} has no upstream branch to push to.")
    remote = upstream.stdout.strip().split("/")[0]

    print(f"Fetching {remote}...")
    run("git", "fetch", "-q", "--tags", remote)
    if git("rev-list", "--count", "HEAD..@{u}") != "0":
        fail(f"{branch} is behind {upstream.stdout.strip()}. Pull first.")

    current = read_version()
    bumped = tag_exists(current) or on_pypi(current)
    version = next_version(current, "patch") if bumped else current
    tag = f"v{version}"
    if tag_exists(version):
        fail(f"tag {tag} already exists.")
    if on_pypi(version):
        fail(f"PyPI already has {PACKAGE} {version}.")

    if bumped:
        print(f"Bumping {current} -> {version}")
        commit_version(version, f"Release {version}")
    else:
        print(f"Releasing {version} as set in pyproject.toml (it has no release yet)")
    run("git", "tag", "-a", tag, "-m", f"{PACKAGE} {version}")

    # Atomic: the commit and the tag land together or not at all. If the remote
    # refuses the push, undo the local commit and tag, so a second run is safe.
    print(f"Pushing {branch} and tag {tag} to {remote}...")
    pushed = run("git", "push", "--atomic", remote, f"HEAD:refs/heads/{branch}", f"refs/tags/{tag}", check=False, quiet=False)
    if pushed.returncode != 0:
        run("git", "tag", "-d", tag)
        if bumped:
            run("git", "reset", "-q", "--keep", "HEAD~1")
        fail("the remote refused the push. The local commit and tag are undone.")

    print(f"\nPushed {tag}. The Publish workflow tests, builds and uploads it to PyPI.")
    if url := repo_url(remote):
        print(f"Follow it at {url}/actions/workflows/{WORKFLOW}")


def bump(part: str | None) -> None:
    if part not in ("minor", "major"):
        fail("bump takes minor or major. make publish bumps the patch.")
    require_clean()
    version = next_version(read_version(), part)  # type: ignore[arg-type]
    commit_version(version, f"Start {version}")
    print(f"pyproject.toml is now {version}, committed and not tagged. make publish releases it.")


if __name__ == "__main__":
    command, arg = (sys.argv[1:] + [None, None])[:2]
    if command == "publish":
        publish()
    elif command == "bump":
        bump(arg)
    else:
        fail("usage: python scripts/release.py publish | bump minor|major")
