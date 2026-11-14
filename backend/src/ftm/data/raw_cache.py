"""Immutable raw snapshot store (DEVELOPMENT_GUIDE.md section 6: never overwrite source values)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ftm.config import get_settings
from ftm.provenance import sha256_bytes


class RawSnapshotExistsError(FileExistsError):
    """Raised when writing would overwrite an existing raw snapshot."""


@dataclass(frozen=True)
class RawSnapshot:
    path: Path  # absolute path on disk
    relative_path: str  # path relative to data/, stored in the DB
    sha256: str
    retrieved_at: datetime


def save_raw(source_key: str, filename: str, content: bytes, raw_dir: Path | None = None) -> RawSnapshot:
    """Write a downloaded payload to ``data/raw/<source_key>/<YYYY-MM-DD>/<filename>``.

    Refuses to overwrite existing files: a re-download gets a new filename or date.
    """
    root = raw_dir or get_settings().raw_dir
    retrieved_at = datetime.now(UTC)
    target = root / source_key / retrieved_at.strftime("%Y-%m-%d") / filename
    if target.exists():
        raise RawSnapshotExistsError(f"Raw snapshot already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as fh:  # 'x' = fail if it appeared in the meantime
        fh.write(content)
    target.chmod(0o444)
    return RawSnapshot(
        path=target,
        # POSIX separators so DB-stored paths are identical across Windows/Linux machines.
        relative_path=target.relative_to(root.parent).as_posix(),
        sha256=sha256_bytes(content),
        retrieved_at=retrieved_at,
    )
