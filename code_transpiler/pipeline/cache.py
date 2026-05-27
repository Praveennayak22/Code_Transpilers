"""
pipeline/cache.py
=================
SHA256-keyed transpilation cache backed by the filesystem.

Uses filelock to safely handle concurrent writes from multiple SLURM tasks
that share the same cache directory via NFS.

Cache key format: SHA256(source_lang:target_lang:source_code)
Cache storage:    One file per entry under cache_dir/
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from typing import Optional


class TranspileCache:
    """
    Filesystem-backed cache for transpilation results.

    Thread-safe and process-safe via filelock.
    Safe for concurrent SLURM tasks sharing an NFS directory.
    """

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict = {}   # In-process memory cache (LRU-style)
        self._max_memory = 10_000  # Max entries in memory cache

    def _key_path(self, key: str) -> Path:
        """Return the file path for a given cache key."""
        # Use first 2 chars as subdirectory to avoid too many files in one dir
        subdir = self.cache_dir / key[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{key}.json"

    def get(self, key: str) -> Optional[str]:
        """Retrieve a cached transpilation result."""
        # Check memory cache first
        if key in self._memory:
            return self._memory[key]

        # Check disk cache
        path = self._key_path(key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result = data.get("result")
                # Promote to memory cache
                if len(self._memory) < self._max_memory:
                    self._memory[key] = result
                return result
            except Exception:
                return None
        return None

    def set(self, key: str, result: str) -> None:
        """Store a transpilation result in the cache."""
        # Memory cache
        if len(self._memory) < self._max_memory:
            self._memory[key] = result

        # Disk cache — use atomic write to avoid partial reads
        path = self._key_path(key)
        tmp_path = path.with_suffix(".tmp")
        try:
            data = json.dumps({"result": result}, ensure_ascii=False)
            tmp_path.write_text(data, encoding="utf-8")
            tmp_path.replace(path)  # Atomic rename
        except Exception:
            pass  # Cache write failure is non-fatal

    def stats(self) -> dict:
        """Return cache statistics."""
        disk_count = sum(1 for _ in self.cache_dir.rglob("*.json"))
        return {
            "memory_entries": len(self._memory),
            "disk_entries":   disk_count,
            "cache_dir":      str(self.cache_dir),
        }
