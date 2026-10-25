"""scripts/release.py moves every version line together, and nothing else."""

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def test_write_version_updates_every_version_file(tmp_path: Path) -> None:
    for rel in release.VERSION_FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    new = release.next_version(release.read_version(tmp_path), "patch")

    release.write_version(new, tmp_path)

    for rel in release.VERSION_FILES:
        before = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        after = (tmp_path / rel).read_text(encoding="utf-8").splitlines()
        # Only the version line changes: target-version, python_version and others stay.
        changed = [a for a, b in zip(after, before, strict=True) if a != b]
        assert len(changed) == 1 and new in changed[0]


def test_next_version() -> None:
    assert release.next_version("1.2.3", "patch") == "1.2.4"
    assert release.next_version("1.2.3", "minor") == "1.3.0"
    assert release.next_version("1.2.3", "major") == "2.0.0"
