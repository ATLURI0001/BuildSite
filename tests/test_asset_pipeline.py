"""Unit tests for AssetPipeline, SRI hashing, and compression diagnostics."""

import pytest
from buildsite.asset_pipeline import AssetPipeline


def test_fingerprint_path_generation():
    pipeline = AssetPipeline()
    content = b"console.log('hello world');"
    fingerprinted = pipeline.fingerprint_path("assets/app.js", content)

    assert fingerprinted.startswith("assets/app.")
    assert fingerprinted.endswith(".js")
    # Same content yields identical fingerprint (deterministic)
    assert fingerprinted == pipeline.fingerprint_path("assets/app.js", content)


def test_fingerprint_path_traversal_rejection():
    pipeline = AssetPipeline()
    with pytest.raises(ValueError, match="clean relative path"):
        pipeline.fingerprint_path("../secret.js", b"data")

    with pytest.raises(ValueError, match="clean relative path"):
        pipeline.fingerprint_path("/absolute/path.js", b"data")


def test_sri_hash_format():
    pipeline = AssetPipeline()
    content = b"alert(1);"
    sri = pipeline.compute_sri_hash(content)

    assert sri.startswith("sha384-")
    # sha384 base64 has length 64 chars -> total len 71
    assert len(sri) == 71


def test_compression_analysis():
    pipeline = AssetPipeline()
    # High redundancy text -> highly compressible
    text_content = b"A" * 1000 + b"B" * 1000
    profile = pipeline.analyze_compression(text_content)

    assert profile["raw_size_bytes"] == 2000
    assert profile["gzip_size_bytes"] < 100
    assert profile["savings_ratio"] > 0.90
    assert profile["is_compressible"] is True
    assert profile["shannon_entropy"] == 1.0  # Exactly 2 symbols equally distributed


def test_empty_content_analysis():
    pipeline = AssetPipeline()
    profile = pipeline.analyze_compression(b"")

    assert profile["raw_size_bytes"] == 0
    assert profile["gzip_size_bytes"] == 0
    assert profile["savings_ratio"] == 0.0
    assert profile["shannon_entropy"] == 0.0
    assert profile["is_compressible"] is False


def test_generate_manifest():
    pipeline = AssetPipeline(cache_max_age_sec=86400)
    assets = {
        "styles/theme.css": b"body { background: #fff; margin: 0; }",
        "scripts/main.js": b"function init() { return true; }",
    }

    manifest = pipeline.generate_manifest(assets)
    assert "styles/theme.css" in manifest
    assert "scripts/main.js" in manifest

    css_entry = manifest["styles/theme.css"]
    assert css_entry["content_type"] == "text/css"
    assert "public, max-age=86400, immutable" in css_entry["cache_control"]
    assert css_entry["sri_hash"].startswith("sha384-")
    assert "styles/theme." in css_entry["fingerprinted_path"]
