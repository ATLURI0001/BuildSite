"""
BuildSite Asset Specification Contract & Path Traversal Boundary Sanitizer

Enforces formal asset schema invariants, path traversal defenses,
SRI integrity hash verification, and MIME-type conformance for static site deployment manifests.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


class AssetContractViolationError(Exception):
    def __init__(self, message: str, code: str, field_name: str) -> None:
        super().__init__(f"[{code}] {field_name}: {message}")
        self.code = code
        self.field_name = field_name


# Whitelisted static asset MIME types
ALLOWED_CONTENT_TYPES: Set[str] = {
    "text/css",
    "application/javascript",
    "application/json",
    "image/svg+xml",
    "image/png",
    "image/jpeg",
    "image/webp",
    "font/woff2",
    "font/woff",
    "text/plain",
}

# Subresource Integrity (SRI) pattern: sha256-, sha384-, sha512-
SRI_HASH_PATTERN = re.compile(r"^(?:sha256|sha384|sha512)-[A-Za-z0-9+/=]{43,88}$")

ASSET_ID_PATTERN = re.compile(r"^asset-[a-zA-Z0-9_-]{3,64}$")
PATH_TRAVERSAL_PATTERN = re.compile(r"(?:\.\.[\\/]|[\\/]\.\.|^\.\.$|%2e%2e|\x00)")
ALLOWED_EXTENSIONS: Set[str] = {
    ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff2", ".woff", ".txt"
}


@dataclass(frozen=True)
class ValidatedAssetSpec:
    asset_id: str
    file_path: str
    content_type: str
    size_bytes: int
    sri_hash: str
    cache_control: str
    is_immutable: bool


@dataclass(frozen=True)
class ValidatedAssetManifest:
    manifest_id: str
    assets: List[ValidatedAssetSpec]
    total_assets: int
    total_size_bytes: int
    canonical_checksum: str


def sanitize_relative_path(path_str: str) -> str:
    """
    Sanitizes and normalizes relative file paths, rejecting traversal attempts and null bytes.
    """
    if not isinstance(path_str, str) or not path_str.strip():
        raise AssetContractViolationError("File path must be a non-empty string", "ERR_INVALID_PATH", "file_path")

    # Reject null bytes and path traversal patterns
    if PATH_TRAVERSAL_PATTERN.search(path_str):
        raise AssetContractViolationError(
            f"Path traversal or null-byte detected in path: '{path_str}'",
            "ERR_PATH_TRAVERSAL",
            "file_path",
        )

    # Normalize slashes and resolve dots
    cleaned = path_str.replace("\\", "/").strip()
    if cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")

    normalized = posixpath.normpath(cleaned)
    if normalized == "." or normalized.startswith("..") or "/../" in normalized:
        raise AssetContractViolationError(
            f"Path escapes root directory after normalization: '{path_str}'",
            "ERR_PATH_ESCAPE",
            "file_path",
        )

    # Validate file extension
    _, ext = posixpath.splitext(normalized)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise AssetContractViolationError(
            f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            "ERR_UNSUPPORTED_EXTENSION",
            "file_path",
        )

    return normalized


def validate_asset_spec(data: Dict[str, Any]) -> ValidatedAssetSpec:
    """
    Validates a single asset specification against formal ingress boundary invariants.
    """
    if not isinstance(data, dict):
        raise AssetContractViolationError("Asset specification must be a dictionary", "ERR_INVALID_SPEC", "spec")

    # 1. Asset ID
    asset_id = str(data.get("asset_id", "")).strip()
    if not ASSET_ID_PATTERN.match(asset_id):
        raise AssetContractViolationError(
            f"asset_id must match 'asset-<id>' [3-64 chars], got '{asset_id}'",
            "ERR_INVALID_ASSET_ID",
            "asset_id",
        )

    # 2. File Path & Traversal Guard
    file_path = sanitize_relative_path(str(data.get("file_path", "")))

    # 3. Content Type Whitelist
    content_type = str(data.get("content_type", "")).lower().strip()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise AssetContractViolationError(
            f"Unsupported content_type '{content_type}'. Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
            "ERR_INVALID_CONTENT_TYPE",
            "content_type",
        )

    # 4. Size bounds: 1 byte to 50 MB
    try:
        size_bytes = int(data.get("size_bytes", 0))
    except (ValueError, TypeError):
        raise AssetContractViolationError("size_bytes must be an integer", "ERR_INVALID_SIZE", "size_bytes")

    max_size = 50 * 1024 * 1024
    if size_bytes <= 0 or size_bytes > max_size:
        raise AssetContractViolationError(
            f"size_bytes must be between 1 and {max_size} bytes (50MB), got {size_bytes}",
            "ERR_SIZE_OUT_OF_BOUNDS",
            "size_bytes",
        )

    # 5. SRI Hash validation
    sri_hash = str(data.get("sri_hash", "")).strip()
    if not SRI_HASH_PATTERN.match(sri_hash):
        raise AssetContractViolationError(
            f"sri_hash must match 'sha256/384/512-<base64>' format, got '{sri_hash}'",
            "ERR_INVALID_SRI_HASH",
            "sri_hash",
        )

    # 6. Cache Control & Immutability
    cache_control = str(data.get("cache_control", "public, max-age=31536000, immutable")).strip()
    is_immutable = "immutable" in cache_control.lower()

    return ValidatedAssetSpec(
        asset_id=asset_id,
        file_path=file_path,
        content_type=content_type,
        size_bytes=size_bytes,
        sri_hash=sri_hash,
        cache_control=cache_control,
        is_immutable=is_immutable,
    )


def validate_asset_manifest(manifest_dict: Dict[str, Any]) -> ValidatedAssetManifest:
    """
    Validates a complete site asset manifest and generates a deterministic canonical checksum.
    """
    if not isinstance(manifest_dict, dict):
        raise AssetContractViolationError("Manifest must be a dictionary", "ERR_INVALID_MANIFEST", "manifest")

    manifest_id = str(manifest_dict.get("manifest_id", "")).strip()
    if not manifest_id or len(manifest_id) > 64:
        raise AssetContractViolationError("manifest_id must be between 1 and 64 characters", "ERR_INVALID_MANIFEST_ID", "manifest_id")

    raw_assets = manifest_dict.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) == 0:
        raise AssetContractViolationError("assets must be a non-empty list", "ERR_EMPTY_ASSET_LIST", "assets")

    if len(raw_assets) > 500:
        raise AssetContractViolationError("assets list exceeds maximum limit of 500 entries", "ERR_ASSET_CAPACITY_EXCEEDED", "assets")

    seen_ids: Set[str] = set()
    seen_paths: Set[str] = set()
    validated_assets: List[ValidatedAssetSpec] = []
    total_size = 0

    for i, raw_item in enumerate(raw_assets):
        spec = validate_asset_spec(raw_item)
        if spec.asset_id in seen_ids:
            raise AssetContractViolationError(f"Duplicate asset_id '{spec.asset_id}' at index {i}", "ERR_DUPLICATE_ASSET_ID", f"assets[{i}]")
        if spec.file_path in seen_paths:
            raise AssetContractViolationError(f"Duplicate file_path '{spec.file_path}' at index {i}", "ERR_DUPLICATE_FILE_PATH", f"assets[{i}]")

        seen_ids.add(spec.asset_id)
        seen_paths.add(spec.file_path)
        validated_assets.append(spec)
        total_size += spec.size_bytes

    # Canonical checksum computation
    canonical_repr = [
        {
            "id": a.asset_id,
            "path": a.file_path,
            "type": a.content_type,
            "size": a.size_bytes,
            "sri": a.sri_hash,
        }
        for a in validated_assets
    ]
    canonical_json = json.dumps(canonical_repr, sort_keys=True)
    checksum = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return ValidatedAssetManifest(
        manifest_id=manifest_id,
        assets=validated_assets,
        total_assets=len(validated_assets),
        total_size_bytes=total_size,
        canonical_checksum=checksum,
    )
