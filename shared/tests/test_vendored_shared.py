"""Guard against drift between shared/xleuth_shared and its vendored copies.

The deploy BuildService builds each service with that service's own directory
as the build context, so shared/xleuth_shared/ is vendored into every service
directory by scripts/sync-shared.sh. These tests fail if someone edits
shared/xleuth_shared/ and forgets to re-run the sync.
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "shared" / "xleuth_shared"
SERVICES = ("data-ingestion", "backend-api", "matching-engine", "oracle-service")

IGNORED = {"__pycache__", ".pytest_cache"}


def _files(root: Path) -> set[str]:
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and not (IGNORED & set(p.parts)) and p.suffix != ".pyc"
    }


def _assert_in_sync(service: str) -> None:
    vendored = REPO_ROOT / service / "shared" / "xleuth_shared"
    assert vendored.is_dir(), (
        f"{service}/shared/xleuth_shared/ is missing — "
        f"run scripts/sync-shared.sh"
    )
    src_files, dst_files = _files(SOURCE), _files(vendored)
    assert src_files == dst_files, (
        f"{service}/shared/xleuth_shared/ is out of sync with shared/xleuth_shared/.\n"
        f"  only in source:   {sorted(src_files - dst_files)}\n"
        f"  only in vendored: {sorted(dst_files - src_files)}\n"
        f"Run scripts/sync-shared.sh and commit the result."
    )
    match, mismatch, errors = filecmp.cmpfiles(
        SOURCE, vendored, src_files, shallow=False
    )
    assert not mismatch and not errors, (
        f"{service}/shared/xleuth_shared/ content differs from shared/xleuth_shared/ "
        f"in: {sorted(mismatch)} — run scripts/sync-shared.sh"
    )


@pytest.mark.parametrize("service", SERVICES)
def test_vendored_shared_matches_source(service: str) -> None:
    _assert_in_sync(service)