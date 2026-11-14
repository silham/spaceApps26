"""Run IDs and checksums used to trace every output back to its inputs (AGENTS.md rule 2)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def new_id(prefix: str) -> str:
    """Return a sortable, unique ID such as ``sim_20261114T120301Z_3f9a1c2b``."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def inputs_hash(payload: dict[str, Any]) -> str:
    """Stable hash of run inputs, used as a result-cache key."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_bytes(canonical.encode())
