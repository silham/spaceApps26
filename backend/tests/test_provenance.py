from pathlib import Path

import pytest

from ftm.data.raw_cache import RawSnapshotExistsError, save_raw
from ftm.provenance import inputs_hash, new_id, sha256_bytes, sha256_file


def test_raw_snapshot_is_checksummed_and_read_only(tmp_path: Path) -> None:
    snap = save_raw("power", "site.json", b'{"a": 1}', raw_dir=tmp_path / "raw")
    assert snap.sha256 == sha256_bytes(b'{"a": 1}') == sha256_file(snap.path)
    assert snap.relative_path.startswith("raw/power/")
    assert not snap.path.stat().st_mode & 0o222, "raw snapshots must be read-only"


def test_raw_snapshot_never_overwrites(tmp_path: Path) -> None:
    save_raw("power", "site.json", b"first", raw_dir=tmp_path / "raw")
    with pytest.raises(RawSnapshotExistsError):
        save_raw("power", "site.json", b"second", raw_dir=tmp_path / "raw")


def test_inputs_hash_is_order_independent() -> None:
    assert inputs_hash({"a": 1, "b": [1, 2]}) == inputs_hash({"b": [1, 2], "a": 1})


def test_new_id_prefix_and_uniqueness() -> None:
    ids = {new_id("sim") for _ in range(100)}
    assert len(ids) == 100 and all(i.startswith("sim_") for i in ids)
