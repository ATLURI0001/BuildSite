"""Compositing engine for BuildSite.

Blends architectural render layers, applies deterministic material tinting,
evaluates lighting passes (daytime, dusk, night), and produces unified high-resolution
composite property images.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageEnhance

from buildsite.models import PropertyState, PropertyVariation, UserConfig
from buildsite.property import derive_property_variation, get_style_palette_by_name

logger = logging.getLogger(__name__)


def find_assets_directory() -> Path:
    """Locate the bundled assets directory."""
    import os

    # 0. Environment variable override
    env_dir = os.environ.get("BUILDSITE_ASSETS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)

    candidates = [
        # 1. Bundled package assets (inside buildsite/assets)
        Path(__file__).resolve().parent / "assets",
        # 2. Development source root (when running from source / git repo)
        Path(__file__).resolve().parent.parent.parent / "assets",
        # 3. Current working directory or parent directories
        Path.cwd() / "assets",
        Path.cwd() / "buildsite" / "assets",
        Path.cwd().parent / "assets",
    ]
    for c in candidates:
        if (c / "manifests" / "layer_manifest.json").is_file():
            return c
        if (c / "environment" / "plot_base.png").is_file():
            return c
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def load_layer_manifest(assets_dir: Path | str) -> Dict[str, Any]:
    """Load the layer manifest if present."""
    base_dir = Path(assets_dir)
    manifest_path = base_dir / "manifests" / "layer_manifest.json"
    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not read layer manifest %s: %s", manifest_path, exc)
    return {"layers": {}}


def resolve_layer_path(layer_name: str, assets_dir: Path | str, manifest: Dict[str, Any]) -> Optional[Path]:
    """Resolve file path for a specific layer name."""
    clean_layer = str(layer_name or "").strip()
    if not clean_layer:
        return None
    base_dir = Path(assets_dir)
    # Check manifest first
    layer_info = manifest.get("layers", {}).get(clean_layer)
    if layer_info and "file" in layer_info:
        cand = base_dir / layer_info["file"]
        if cand.is_file():
            return cand

    # Direct search across subdirectories
    subdirs = ["architecture", "environment", "landscaping", "pool", ""]
    for s in subdirs:
        cand = base_dir / s / f"{clean_layer}.png"
        if cand.is_file():
            return cand

    return None


def apply_dusk_lighting(base_img: Image.Image, emissive_img: Image.Image) -> Image.Image:
    """Simulate evening twilight with warm ambient shading and glowing emissive windows/lights."""
    # Color grade base image towards golden dusk / twilight blue
    # Create subtle warm tint overlay (RGB: 250, 190, 140)
    width, height = base_img.size
    dusk_grade = Image.new("RGBA", (width, height), (35, 30, 60, 60))
    graded = Image.alpha_composite(base_img, dusk_grade)

    # Blend the emissive lights on top
    composite = Image.alpha_composite(graded, emissive_img)
    return composite


def composite_property(
    state: Optional[PropertyState],
    config: Optional[UserConfig] = None,
    assets_dir: Optional[Path | str] = None,
    variation: Optional[PropertyVariation] = None
) -> Image.Image:
    """Composite the active architectural layers into a finished property rendering.

    Args:
        state: Current property state containing active layers and progress.
        config: Rendering and user configuration.
        assets_dir: Optional directory containing asset files (Path or str).
        variation: Optional deterministic variation; derived if None.

    Returns:
        Pillow Image in RGBA format (1280x640 default).
    """
    cfg = config if config is not None else UserConfig()
    target_w = max(1, int(cfg.width or 1280))
    target_h = max(1, int(cfg.height or 640))

    if state is None:
        return Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    actual_assets_dir = Path(assets_dir) if assets_dir else find_assets_directory()
    manifest = load_layer_manifest(actual_assets_dir)

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    actual_variation = variation or derive_property_variation(state.seed, cfg.style)

    for layer_name in state.active_layers:
        layer_path = resolve_layer_path(layer_name, actual_assets_dir, manifest)
        if not layer_path:
            logger.warning("Layer '%s' asset not found in %s", layer_name, actual_assets_dir)
            continue

        try:
            layer_img = Image.open(layer_path).convert("RGBA")
            if layer_img.size != (target_w, target_h):
                layer_img = layer_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            canvas = Image.alpha_composite(canvas, layer_img)
        except Exception as exc:
            logger.error("Failed to load and composite layer %s: %s", layer_path, exc)

    # Apply lighting pass
    if config.lighting in {"dusk", "night"}:
        emissive_path = resolve_layer_path("dusk_emissive", actual_assets_dir, manifest)
        if emissive_path and emissive_path.is_file():
            try:
                emissive_img = Image.open(emissive_path).convert("RGBA")
                if emissive_img.size != (target_w, target_h):
                    emissive_img = emissive_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                canvas = apply_dusk_lighting(canvas, emissive_img)
            except Exception as exc:
                logger.warning("Failed to composite dusk emissive pass: %s", exc)

    return canvas
