"""Static Asset Cache Optimizer, SRI Fingerprinter & Compression Ratio Profiler.

Generates immutable content-addressable filenames, subresource integrity (SRI)
hashes, and gzip compression diagnostics for static site generation.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import math
import mimetypes
from pathlib import PurePosixPath
from typing import Dict, Optional


class AssetPipeline:
    """Processes static assets for immutable production caching and integrity verification."""

    def __init__(self, cache_max_age_sec: int = 31536000):
        self.cache_max_age_sec = cache_max_age_sec

    def fingerprint_path(self, relative_path: str, content: bytes) -> str:
        """Returns content-addressed path with 8-character hash slug."""
        if not relative_path or not isinstance(relative_path, str):
            raise ValueError("relative_path must be a non-empty string")
        if ".." in relative_path or relative_path.startswith("/"):
            raise ValueError("relative_path must be a clean relative path without traversal")

        path_obj = PurePosixPath(relative_path)
        digest = hashlib.sha256(content).hexdigest()[:8]
        stem = path_obj.stem
        suffix = path_obj.suffix

        if path_obj.parent == PurePosixPath("."):
            return f"{stem}.{digest}{suffix}"
        return f"{path_obj.parent}/{stem}.{digest}{suffix}"

    def compute_sri_hash(self, content: bytes) -> str:
        """Computes W3C Subresource Integrity (SRI) sha384 checksum."""
        digest = hashlib.sha384(content).digest()
        b64 = base64.b64encode(digest).decode("ascii")
        return f"sha384-{b64}"

    def compute_byte_entropy(self, content: bytes) -> float:
        """Computes Shannon entropy over byte frequency distribution (in bits/byte)."""
        if not content:
            return 0.0

        freq: Dict[int, int] = {}
        for b in content:
            freq[b] = freq.get(b, 0) + 1

        total = len(content)
        entropy = 0.0
        for count in freq.values():
            p = count / total
            entropy -= p * math.log2(p)

        return round(entropy, 4)

    def analyze_compression(self, content: bytes) -> Dict[str, object]:
        """Analyzes compressibility and simulates gzip compression efficiency."""
        raw_size = len(content)
        if raw_size == 0:
            return {
                "raw_size_bytes": 0,
                "gzip_size_bytes": 0,
                "savings_ratio": 0.0,
                "shannon_entropy": 0.0,
                "is_compressible": False,
            }

        compressed = gzip.compress(content, compresslevel=9)
        gzip_size = len(compressed)
        savings = round(max(0.0, 1.0 - (gzip_size / raw_size)), 4)
        entropy = self.compute_byte_entropy(content)

        return {
            "raw_size_bytes": raw_size,
            "gzip_size_bytes": gzip_size,
            "savings_ratio": savings,
            "shannon_entropy": entropy,
            "is_compressible": savings >= 0.15,
        }

    def generate_manifest(self, asset_map: Dict[str, bytes]) -> Dict[str, object]:
        """Generates production asset manifest with fingerprints, SRI, and cache headers."""
        manifest: Dict[str, object] = {}

        for orig_path, data in asset_map.items():
            if not isinstance(data, (bytes, bytearray)):
                continue

            content_bytes = bytes(data)
            fingerprinted = self.fingerprint_path(orig_path, content_bytes)
            sri = self.compute_sri_hash(content_bytes)
            comp_profile = self.analyze_compression(content_bytes)

            mime_type, _ = mimetypes.guess_type(orig_path)
            content_type = mime_type or "application/octet-stream"

            manifest[orig_path] = {
                "fingerprinted_path": fingerprinted,
                "sri_hash": sri,
                "content_type": content_type,
                "cache_control": f"public, max-age={self.cache_max_age_sec}, immutable",
                "compression": comp_profile,
            }

        return manifest
