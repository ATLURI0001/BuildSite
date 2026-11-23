import os
import time
from pathlib import Path
import pytest

from buildsite.atomic_cache_manager import (
    AtomicBuildCacheManager,
    StaleLockError,
)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / "build_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_atomic_cache_put_and_get(cache_dir: Path):
    manager = AtomicBuildCacheManager(cache_dir)
    entry = manager.put("app.bundle.js", b"console.log('hello');", metadata={"version": 1})

    assert entry.key == "app.bundle.js"
    assert entry.size_bytes == 21
    assert len(entry.content_hash) == 64
    assert entry.metadata["version"] == 1

    retrieved = manager.get("app.bundle.js")
    assert retrieved == b"console.log('hello');"

    telemetry = manager.get_telemetry()
    assert telemetry["hits"] == 1
    assert telemetry["misses"] == 0
    assert telemetry["hit_ratio"] == 1.0


def test_atomic_cache_miss_on_unknown_key(cache_dir: Path):
    manager = AtomicBuildCacheManager(cache_dir)
    assert manager.get("nonexistent.css") is None

    telemetry = manager.get_telemetry()
    assert telemetry["hits"] == 0
    assert telemetry["misses"] == 1
    assert telemetry["hit_ratio"] == 0.0


def test_atomic_cache_poisoning_detection(cache_dir: Path):
    manager = AtomicBuildCacheManager(cache_dir)
    manager.put("vendor.js", b"valid_vendor_code")

    # Manually tamper with the cached file on disk to simulate cache corruption / tampering
    key_hash = manager._hash_key("vendor.js")
    target_file = cache_dir / key_hash
    with open(target_file, "wb") as f:
        f.write(b"tampered_malicious_injected_code")

    # get() must detect hash mismatch, purge entry, and return None
    data = manager.get("vendor.js", verify_integrity=True)
    assert data is None

    telemetry = manager.get_telemetry()
    assert telemetry["poisoned_entries_detected"] == 1
    assert not target_file.exists()


def test_atomic_cache_locking_and_stale_recovery(cache_dir: Path):
    manager = AtomicBuildCacheManager(cache_dir, lock_timeout_sec=0.5)

    # Acquire lock
    lock = manager.acquire_lock("build.lock")
    assert lock.exists()

    # Second acquisition must fail
    with pytest.raises(StaleLockError):
        manager.acquire_lock("build.lock")

    # Release lock
    assert manager.release_lock(lock)
    assert not lock.exists()

    # Simulate an orphaned stale lock from crashed worker
    stale_lock = cache_dir / "build.lock"
    with open(stale_lock, "w") as f:
        f.write("99999:0")
    # Backdate mtime by 10 seconds
    past_time = time.time() - 10.0
    os.utime(str(stale_lock), (past_time, past_time))

    # New acquisition should break stale lock automatically
    new_lock = manager.acquire_lock("build.lock")
    assert new_lock.exists()
    telemetry = manager.get_telemetry()
    assert telemetry["stale_locks_cleared"] == 1

    manager.release_lock(new_lock)


def test_atomic_publish_workflow(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    manager = AtomicBuildCacheManager(cache_dir)

    staging = tmp_path / "staging_123"
    staging.mkdir()
    (staging / "index.html").write_text("<h1>Deployed Site</h1>", encoding="utf-8")

    target = tmp_path / "public_html"

    # Initial atomic publish
    assert manager.atomic_publish(staging, target)
    assert (target / "index.html").read_text(encoding="utf-8") == "<h1>Deployed Site</h1>"
    assert not staging.exists()

    # Overwrite atomic publish with new staging content
    staging_v2 = tmp_path / "staging_456"
    staging_v2.mkdir()
    (staging_v2 / "index.html").write_text("<h1>Updated Site v2</h1>", encoding="utf-8")

    assert manager.atomic_publish(staging_v2, target)
    assert (target / "index.html").read_text(encoding="utf-8") == "<h1>Updated Site v2</h1>"

    telemetry = manager.get_telemetry()
    assert telemetry["published_count"] == 2


def test_atomic_cache_clear(cache_dir: Path):
    manager = AtomicBuildCacheManager(cache_dir)
    manager.put("style.css", b"body { color: red; }")
    assert manager.get_telemetry()["active_entries"] == 1

    manager.clear()
    assert manager.get_telemetry()["active_entries"] == 0
    assert manager.get("style.css") is None
