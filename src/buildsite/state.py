"""Evolution state persistence, reconciliation, and schema migration for BuildSite.

Manages saving, loading, verifying, and migrating the user's property state,
ensuring non-destructive updates, duplicate run detection, and deterministic history.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from buildsite.models import ConstructionMilestone, PropertyState

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILENAME = "buildsite_state.json"
CURRENT_SCHEMA_VERSION = 1


class StateError(Exception):
    """Raised when loading or writing state fails."""


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_state(state_file_path: Path | str) -> Optional[PropertyState]:
    """Load and migrate existing PropertyState from disk.

    Returns None if file does not exist or cannot be parsed as a JSON object.
    """
    path = Path(state_file_path)
    if not path.is_file():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("Could not read existing state file %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Expected JSON object in state file %s, got %s", path, type(data).__name__)
        return None

    # Handle schema migration if needed
    schema_ver = _safe_int(data.get("schema_version", 1), 1)
    if schema_ver > CURRENT_SCHEMA_VERSION:
        logger.warning(
            "State file has newer schema version %d than supported %d",
            schema_ver,
            CURRENT_SCHEMA_VERSION
        )

    try:
        milestone_str = data.get("milestone", ConstructionMilestone.PLOT.value)
        milestone = ConstructionMilestone(milestone_str)
    except ValueError:
        milestone = ConstructionMilestone.PLOT

    raw_layers = data.get("active_layers", [])
    raw_unlocked = data.get("unlocked_features", [])

    return PropertyState(
        schema_version=CURRENT_SCHEMA_VERSION,
        user_id=_safe_int(data.get("user_id", 0)),
        login=str(data.get("login", "") or ""),
        seed=str(data.get("seed", "") or ""),
        total_contributions=_safe_int(data.get("total_contributions", 0)),
        active_days=_safe_int(data.get("active_days", 0)),
        milestone=milestone,
        progress_ratio=_safe_float(data.get("progress_ratio", 0.0)),
        active_layers=list(raw_layers) if isinstance(raw_layers, list) else [],
        unlocked_features=list(raw_unlocked) if isinstance(raw_unlocked, list) else [],
        variation=data.get("variation"),
        last_updated=str(data.get("last_updated", "") or ""),
        last_contribution_count=_safe_int(data.get("last_contribution_count", 0)),
        hash_signature=str(data.get("hash_signature", "") or "")
    )


def save_state(state: PropertyState, state_file_path: Path | str) -> None:
    """Save PropertyState to disk atomically."""
    path = Path(state_file_path)
    if path.is_dir():
        raise StateError(f"Target state file path is a directory: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": state.schema_version,
        "user_id": state.user_id,
        "login": state.login,
        "seed": state.seed,
        "total_contributions": state.total_contributions,
        "active_days": state.active_days,
        "milestone": state.milestone.value,
        "progress_ratio": state.progress_ratio,
        "active_layers": state.active_layers,
        "unlocked_features": state.unlocked_features,
        "variation": state.variation,
        "last_updated": state.last_updated,
        "last_contribution_count": state.last_contribution_count,
        "hash_signature": state.hash_signature,
    }

    # Write to temporary file then replace atomically
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        tmp_path.replace(path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def has_state_changed(previous_state: Optional[PropertyState], new_state: PropertyState) -> bool:
    """Check if the new state has meaningful changes requiring asset regeneration."""
    if previous_state is None:
        return True
    if previous_state.hash_signature and new_state.hash_signature:
        return previous_state.hash_signature != new_state.hash_signature
    return (
        previous_state.total_contributions != new_state.total_contributions
        or previous_state.active_days != new_state.active_days
        or previous_state.milestone != new_state.milestone
        or previous_state.progress_ratio != new_state.progress_ratio
        or previous_state.active_layers != new_state.active_layers
        or previous_state.variation != new_state.variation
    )
