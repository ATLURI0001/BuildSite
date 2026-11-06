"""Configuration parser and validator for BuildSite.

Reads and validates user settings from buildsite.yml with strong schema
guarantees and security hardening against path traversal or injection.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from buildsite.models import UserConfig


class ConfigValidationError(Exception):
    """Raised when configuration values are invalid or unsafe."""


VALID_LIGHTING_MODES = {"daytime", "dusk", "night"}
VALID_FORMATS = {"svg", "png"}
VALID_ANIMATION_MODES = {"subtle", "none"}
VALID_VISIBILITIES = {"public", "private"}
VALID_STYLES = {"auto", "modern", "minimal", "timber", "slate", "coastal"}


def sanitize_output_dir(path_str: str) -> str:
    """Sanitize and validate output directory to prevent path traversal."""
    cleaned = path_str.strip()
    if not cleaned:
        return "assets/buildsite"
    # Disallow absolute paths outside project or traversal '../'
    normalized = os.path.normpath(cleaned)
    if os.path.isabs(normalized) or normalized.startswith(".."):
        raise ConfigValidationError(
            f"Unsafe output directory path '{path_str}'. Path must be relative and within the repository."
        )
    return normalized.replace("\\", "/")


def load_config(config_path: Optional[str] = None) -> UserConfig:
    """Load and validate UserConfig from YAML file or default search paths."""
    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    else:
        search_paths.extend([
            Path("buildsite.yml"),
            Path("buildsite.yaml"),
            Path(".buildsite.yml"),
            Path(".github/buildsite.yml")
        ])

    raw_data: Dict[str, Any] = {}
    found_path: Optional[Path] = None

    for p in search_paths:
        if p.is_file():
            found_path = p
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if isinstance(content, dict):
                        raw_data = content
            except Exception as exc:
                raise ConfigValidationError(f"Failed to parse YAML from {p}: {exc}") from exc
            break

    cfg = UserConfig()

    # Extract github section
    gh_sec = raw_data.get("github", {})
    if isinstance(gh_sec, dict):
        cfg.username = str(gh_sec.get("username", "")).strip()
        vis = str(gh_sec.get("visibility", "public")).lower()
        if vis in VALID_VISIBILITIES:
            cfg.visibility = vis

    # Extract property section
    prop_sec = raw_data.get("property", {})
    if isinstance(prop_sec, dict):
        style = str(prop_sec.get("style", "modern")).lower()
        if style in VALID_STYLES:
            cfg.style = style
        cfg.seed = str(prop_sec.get("seed", "auto")).strip()
        cfg.palette = str(prop_sec.get("palette", "natural")).lower()
        cfg.pool = bool(prop_sec.get("pool", True))
        cfg.garden = bool(prop_sec.get("garden", True))
        cfg.garage = bool(prop_sec.get("garage", True))
        lighting = str(prop_sec.get("lighting", "dusk")).lower()
        if lighting in VALID_LIGHTING_MODES:
            cfg.lighting = lighting

    # Extract render section
    render_sec = raw_data.get("render", {})
    if isinstance(render_sec, dict):
        cfg.width = max(400, min(2560, int(render_sec.get("width", 1280))))
        cfg.height = max(200, min(1440, int(render_sec.get("height", 640))))
        fmt = str(render_sec.get("format", "svg")).lower()
        if fmt in VALID_FORMATS:
            cfg.format = fmt
        anim = str(render_sec.get("animation", "subtle")).lower()
        if anim in VALID_ANIMATION_MODES:
            cfg.animation = anim
        cfg.quality = str(render_sec.get("quality", "high")).lower()

    # Extract progression section
    prog_sec = raw_data.get("progression", {})
    if isinstance(prog_sec, dict):
        cfg.preserve_unlocks = bool(prog_sec.get("preserve_unlocks", True))

    # Extract output section
    out_sec = raw_data.get("output", {})
    if isinstance(out_sec, dict):
        raw_dir = str(out_sec.get("directory", "assets/buildsite"))
        cfg.output_dir = sanitize_output_dir(raw_dir)
        cfg.png_fallback = bool(out_sec.get("png_fallback", True))

    return cfg
