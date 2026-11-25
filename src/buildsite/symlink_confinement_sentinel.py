"""SSG Symlink Traversal & Asset Directory Confinement Sentinel.

Guards static site asset ingestion, template resolution, and content bundling
against symlink jailbreak attacks, path traversal, and recursive link loops.
Resolves INC-2026-SITE-8192.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class ConfinementError(Exception):
    """Base exception for asset directory confinement violations."""


class PathTraversalViolationError(ConfinementError):
    """Raised when an asset path attempts directory traversal using ../ or null bytes."""


class SymlinkJailbreakError(ConfinementError):
    """Raised when a symlink resolves to a target outside the confined root directory."""


class SymlinkRecursionLoopError(ConfinementError):
    """Raised when recursive or cyclic symlinks exceed maximum traversal depth."""


class SymlinkConfinementSentinel:
    """Enforces strict path confinement and symlink security within a designated root directory."""

    def __init__(
        self,
        root_dir: str | Path,
        allow_internal_symlinks: bool = True,
        max_traversal_depth: int = 15,
    ):
        self.root_dir = Path(root_dir).resolve()
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Root directory does not exist: {self.root_dir}")
        if not self.root_dir.is_dir():
            raise NotADirectoryError(f"Root directory must be a directory: {self.root_dir}")

        self.allow_internal_symlinks = allow_internal_symlinks
        self.max_traversal_depth = max(1, int(max_traversal_depth))

        # Telemetry metrics
        self._total_scanned = 0
        self._symlinks_evaluated = 0
        self._jailbreaks_intercepted = 0
        self._traversal_attempts_blocked = 0
        self._recursion_loops_intercepted = 0

    def resolve_and_verify(self, candidate_path: str | Path) -> Path:
        """Resolves candidate path and verifies it strictly resides within root_dir."""
        raw_str = str(candidate_path)
        if "\x00" in raw_str:
            self._traversal_attempts_blocked += 1
            raise PathTraversalViolationError(f"Null byte detected in candidate path: '{raw_str}'")

        path_obj = Path(candidate_path)
        
        # If relative, anchor to root_dir
        if not path_obj.is_absolute():
            path_obj = self.root_dir / path_obj

        # Check for symlink before full resolution
        is_symlink = path_obj.is_symlink()
        if is_symlink:
            self._symlinks_evaluated += 1
            if not self.allow_internal_symlinks:
                self._jailbreaks_intercepted += 1
                raise SymlinkJailbreakError(
                    f"Symlinks are disallowed by configuration: '{path_obj}'"
                )

        try:
            # Resolve canonical path (dereference all symlinks)
            resolved = path_obj.resolve()
        except RecursionError:
            self._recursion_loops_intercepted += 1
            raise SymlinkRecursionLoopError(f"Symlink recursion loop detected resolving: '{path_obj}'")

        # Confinement check: resolved path must be relative to root_dir
        try:
            resolved.relative_to(self.root_dir)
        except ValueError:
            if is_symlink:
                self._jailbreaks_intercepted += 1
                raise SymlinkJailbreakError(
                    f"Symlink target '{resolved}' escapes confined root directory '{self.root_dir}'"
                )
            self._traversal_attempts_blocked += 1
            raise PathTraversalViolationError(
                f"Path '{resolved}' escapes confined root directory '{self.root_dir}'"
            )

        self._total_scanned += 1
        return resolved

    def safe_walk(self, sub_dir: Optional[str | Path] = None) -> List[Path]:
        """Recursively walks directory, yielding only verified confined file paths."""
        start_dir = self.resolve_and_verify(sub_dir) if sub_dir else self.root_dir
        if not start_dir.is_dir():
            return [start_dir] if start_dir.is_file() else []

        valid_files: List[Path] = []
        visited_realpaths: Set[Path] = set()

        def _walk(curr: Path, depth: int):
            if depth > self.max_traversal_depth:
                self._recursion_loops_intercepted += 1
                raise SymlinkRecursionLoopError(
                    f"Directory traversal exceeded max depth of {self.max_traversal_depth} at '{curr}'"
                )

            real = curr.resolve()
            if real in visited_realpaths:
                return
            visited_realpaths.add(real)

            try:
                entries = list(os.scandir(curr))
            except PermissionError:
                return

            for entry in entries:
                entry_path = Path(entry.path)
                try:
                    verified = self.resolve_and_verify(entry_path)
                except ConfinementError:
                    # Intercepted violation during walk
                    continue

                if verified.is_file():
                    valid_files.append(verified)
                elif verified.is_dir():
                    _walk(entry_path, depth + 1)

        _walk(start_dir, 1)
        return sorted(valid_files)

    def get_metrics(self) -> Dict[str, Any]:
        """Returns diagnostic telemetry metrics."""
        return {
            "root_dir": str(self.root_dir),
            "total_scanned": self._total_scanned,
            "symlinks_evaluated": self._symlinks_evaluated,
            "jailbreaks_intercepted": self._jailbreaks_intercepted,
            "traversal_attempts_blocked": self._traversal_attempts_blocked,
            "recursion_loops_intercepted": self._recursion_loops_intercepted,
        }
