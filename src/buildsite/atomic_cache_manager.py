"""
Atomic Build Cache Manager & Staging Consistency Sentinel.

Provides deterministic content-addressed caching, cache poisoning verification,
two-phase atomic directory publishing, and automated stale lock recovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class CachePoisoningError(Exception):
    """Raised when a cached asset fails cryptographic integrity verification."""
    pass


class StaleLockError(Exception):
    """Raised when an active build lock blocks an operation."""
    pass


@dataclass
class CacheEntry:
    key: str
    content_hash: str
    size_bytes: int
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AtomicBuildCacheManager:
    """Manages build asset caching with atomic writes, integrity auditing, and deadlock recovery."""

    def __init__(
        self,
        cache_dir: Path | str,
        lock_timeout_sec: float = 30.0,
        max_entries: int = 5000,
    ) -> None:
        self.cache_dir = Path(cache_dir).resolve()
        self.lock_timeout_sec = max(1.0, float(lock_timeout_sec))
        self.max_entries = max(10, int(max_entries))

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.cache_dir / ".metadata"
        self.meta_dir.mkdir(parents=True, exist_ok=True)

        self._hits = 0
        self._misses = 0
        self._poisoned_detected = 0
        self._published_count = 0
        self._stale_locks_cleared = 0

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(
        self,
        key: str,
        data: bytes | str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CacheEntry:
        """Stores data in the cache atomically with cryptographic hash manifest."""
        if not key or not isinstance(key, str):
            raise ValueError("Cache key must be a non-empty string")

        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        content_hash = self._compute_hash(raw_bytes)
        key_hash = self._hash_key(key)

        target_file = self.cache_dir / key_hash
        temp_file = self.cache_dir / f"{key_hash}.tmp.{os.getpid()}"

        try:
            with open(temp_file, "wb") as f:
                f.write(raw_bytes)
            os.replace(temp_file, target_file)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        entry = CacheEntry(
            key=key,
            content_hash=content_hash,
            size_bytes=len(raw_bytes),
            created_at=time.time(),
            metadata=metadata or {},
        )

        meta_file = self.meta_dir / f"{key_hash}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "key": entry.key,
                    "content_hash": entry.content_hash,
                    "size_bytes": entry.size_bytes,
                    "created_at": entry.created_at,
                    "metadata": entry.metadata,
                },
                f,
                indent=2,
            )

        return entry

    def get(self, key: str, verify_integrity: bool = True) -> Optional[bytes]:
        """Retrieves cached data, verifying cryptographic integrity against stored manifest."""
        if not key or not isinstance(key, str):
            self._misses += 1
            return None

        key_hash = self._hash_key(key)
        target_file = self.cache_dir / key_hash
        meta_file = self.meta_dir / f"{key_hash}.json"

        if not target_file.exists() or not meta_file.exists():
            self._misses += 1
            return None

        try:
            with open(target_file, "rb") as f:
                data = f.read()

            if verify_integrity:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                expected_hash = meta.get("content_hash")
                actual_hash = self._compute_hash(data)

                if actual_hash != expected_hash:
                    # Cache poisoning detected!
                    self._poisoned_detected += 1
                    try:
                        target_file.unlink()
                        meta_file.unlink()
                    except OSError:
                        pass
                    return None

            self._hits += 1
            return data
        except Exception:
            self._misses += 1
            return None

    def acquire_lock(self, lock_name: str = "build.lock") -> Path:
        """Acquires an exclusive lock file, breaking orphaned locks exceeding timeout."""
        lock_file = self.cache_dir / lock_name
        now = time.time()

        if lock_file.exists():
            try:
                mtime = lock_file.stat().st_mtime
                if (now - mtime) > self.lock_timeout_sec:
                    # Broken/stale lock from crashed worker
                    lock_file.unlink()
                    self._stale_locks_cleared += 1
                else:
                    raise StaleLockError(f"Active lock held on {lock_name}")
            except FileNotFoundError:
                pass

        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()}:{now}")
            return lock_file
        except FileExistsError:
            raise StaleLockError(f"Concurrent process acquired {lock_name}")

    def release_lock(self, lock_file: Path) -> bool:
        """Releases the acquired lock file."""
        try:
            if lock_file.exists():
                lock_file.unlink()
                return True
        except OSError:
            pass
        return False

    def atomic_publish(self, staging_dir: Path | str, target_dir: Path | str) -> bool:
        """Performs two-phase atomic publish of staging directory to target output."""
        staging = Path(staging_dir).resolve()
        target = Path(target_dir).resolve()

        if not staging.exists():
            raise FileNotFoundError(f"Staging directory does not exist: {staging}")

        target.parent.mkdir(parents=True, exist_ok=True)
        backup_dir = target.parent / f".backup_{target.name}_{int(time.time()*1000)}"

        try:
            if target.exists():
                # Cross-platform rename
                os.replace(str(target), str(backup_dir))

            os.replace(str(staging), str(target))

            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

            self._published_count += 1
            return True
        except Exception as exc:
            # Rollback if backup exists
            if backup_dir.exists() and not target.exists():
                try:
                    os.replace(str(backup_dir), str(target))
                except OSError:
                    pass
            raise RuntimeError(f"Atomic publish failed: {exc}") from exc

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns operational counters for SRE observability."""
        total_requests = self._hits + self._misses
        hit_ratio = round(self._hits / total_requests, 4) if total_requests > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total_requests,
            "hit_ratio": hit_ratio,
            "poisoned_entries_detected": self._poisoned_detected,
            "published_count": self._published_count,
            "stale_locks_cleared": self._stale_locks_cleared,
            "active_entries": len(list(self.meta_dir.glob("*.json"))),
        }

    def clear(self) -> None:
        """Purges all cached data and metadata."""
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
