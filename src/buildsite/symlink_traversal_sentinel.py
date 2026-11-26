"""INC-2026-BUILD-3109: Symlink & Path Traversal Escape Sentinel.

Guards static site asset copiers against directory traversal (`../`) and
outbound symlink escapes outside the workspace root.
"""

from __future__ import annotations

import os
from pathlib import Path


class SymlinkTraversalSentinel:
    def __init__(self, workspace_root: str) -> None:
        self.root = Path(workspace_root).resolve()

    def is_safe_path(self, candidate_path: str) -> tuple[bool, str]:
        if ".." in Path(candidate_path).parts:
            return False, "ERR_PATH_TRAVERSAL_SEGMENT"
        resolved = (self.root / candidate_path).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            return False, "ERR_WORKSPACE_ESCAPE"
        return True, "OK"
