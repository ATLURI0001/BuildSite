import pytest
from buildsite.asset_spec_contract import (
    AssetContractViolationError,
    ValidatedAssetSpec,
    ValidatedAssetManifest,
    sanitize_relative_path,
    validate_asset_spec,
    validate_asset_manifest,
)


def test_sanitize_relative_path_valid():
    assert sanitize_relative_path("assets/css/style.css") == "assets/css/style.css"
    assert sanitize_relative_path("static\\js\\main.mjs") == "static/js/main.mjs"
    assert sanitize_relative_path("/images/logo.png") == "images/logo.png"
    assert sanitize_relative_path("fonts/inter.woff2") == "fonts/inter.woff2"


@pytest.mark.parametrize(
    "traversal_attempt",
    [
        "../etc/passwd.txt",
        "..\\windows\\system32.txt",
        "assets/../../secret.json",
        "assets/%2e%2e/config.json",
        "assets/clean.css\x00.exe",
        "public/../..",
    ],
)
def test_sanitize_relative_path_traversal_rejections(traversal_attempt):
    with pytest.raises(AssetContractViolationError) as exc_info:
        sanitize_relative_path(traversal_attempt)
    assert exc_info.value.code in ("ERR_PATH_TRAVERSAL", "ERR_PATH_ESCAPE")


@pytest.mark.parametrize("bad_ext", ["script.sh", "malware.exe", "bundle.tar.gz", "config.yml"])
def test_sanitize_relative_path_unsupported_extension(bad_ext):
    with pytest.raises(AssetContractViolationError) as exc_info:
        sanitize_relative_path(bad_ext)
    assert exc_info.value.code == "ERR_UNSUPPORTED_EXTENSION"


def test_validate_asset_spec_success():
    spec = {
        "asset_id": "asset-main-bundle",
        "file_path": "dist/bundle.js",
        "content_type": "application/javascript",
        "size_bytes": 1048576,
        "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        "cache_control": "public, max-age=31536000, immutable",
    }
    validated = validate_asset_spec(spec)
    assert validated.asset_id == "asset-main-bundle"
    assert validated.file_path == "dist/bundle.js"
    assert validated.content_type == "application/javascript"
    assert validated.size_bytes == 1048576
    assert validated.is_immutable is True


def test_validate_asset_spec_invalid_asset_id():
    spec = {
        "asset_id": "bad_id_without_prefix",
        "file_path": "dist/bundle.js",
        "content_type": "application/javascript",
        "size_bytes": 1024,
        "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_spec(spec)
    assert exc_info.value.code == "ERR_INVALID_ASSET_ID"
    assert exc_info.value.field_name == "asset_id"


def test_validate_asset_spec_unsupported_content_type():
    spec = {
        "asset_id": "asset-binary-blob",
        "file_path": "dist/app.txt",
        "content_type": "application/x-executable",
        "size_bytes": 1024,
        "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_spec(spec)
    assert exc_info.value.code == "ERR_INVALID_CONTENT_TYPE"


@pytest.mark.parametrize("size", [0, -100, 50 * 1024 * 1024 + 1])
def test_validate_asset_spec_size_bounds(size):
    spec = {
        "asset_id": "asset-test-size",
        "file_path": "dist/style.css",
        "content_type": "text/css",
        "size_bytes": size,
        "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_spec(spec)
    assert exc_info.value.code == "ERR_SIZE_OUT_OF_BOUNDS"


@pytest.mark.parametrize(
    "bad_sri",
    [
        "md5-abcd",
        "sha1-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
        "sha256-invalid!chars@#",
        "plain-text-string",
    ],
)
def test_validate_asset_spec_sri_hash(bad_sri):
    spec = {
        "asset_id": "asset-test-sri",
        "file_path": "dist/style.css",
        "content_type": "text/css",
        "size_bytes": 1024,
        "sri_hash": bad_sri,
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_spec(spec)
    assert exc_info.value.code == "ERR_INVALID_SRI_HASH"


def test_validate_asset_manifest_success():
    manifest_data = {
        "manifest_id": "manifest-v2026-prod",
        "assets": [
            {
                "asset_id": "asset-main-css",
                "file_path": "static/css/app.css",
                "content_type": "text/css",
                "size_bytes": 4096,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
                "cache_control": "public, max-age=31536000, immutable",
            },
            {
                "asset_id": "asset-main-js",
                "file_path": "static/js/app.js",
                "content_type": "application/javascript",
                "size_bytes": 8192,
                "sri_hash": "sha384-dGVzdF9zaGEzODRfaGFzaF92YWx1ZV9mb3JfdGVzdGluZ19wdXJwb3Nlc18xMjM0NTY3ODk=",
                "cache_control": "public, max-age=31536000, immutable",
            },
        ],
    }
    manifest = validate_asset_manifest(manifest_data)
    assert manifest.manifest_id == "manifest-v2026-prod"
    assert manifest.total_assets == 2
    assert manifest.total_size_bytes == 12288
    assert len(manifest.canonical_checksum) == 64  # SHA-256


def test_validate_asset_manifest_duplicate_asset_id():
    manifest_data = {
        "manifest_id": "manifest-dup-id",
        "assets": [
            {
                "asset_id": "asset-duplicate",
                "file_path": "static/css/a.css",
                "content_type": "text/css",
                "size_bytes": 100,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
            },
            {
                "asset_id": "asset-duplicate",
                "file_path": "static/css/b.css",
                "content_type": "text/css",
                "size_bytes": 200,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
            },
        ],
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_manifest(manifest_data)
    assert exc_info.value.code == "ERR_DUPLICATE_ASSET_ID"


def test_validate_asset_manifest_duplicate_file_path():
    manifest_data = {
        "manifest_id": "manifest-dup-path",
        "assets": [
            {
                "asset_id": "asset-first",
                "file_path": "static/common.css",
                "content_type": "text/css",
                "size_bytes": 100,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
            },
            {
                "asset_id": "asset-second",
                "file_path": "static/common.css",
                "content_type": "text/css",
                "size_bytes": 200,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
            },
        ],
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_manifest(manifest_data)
    assert exc_info.value.code == "ERR_DUPLICATE_FILE_PATH"


def test_validate_asset_manifest_capacity_exceeded():
    manifest_data = {
        "manifest_id": "manifest-overflow",
        "assets": [
            {
                "asset_id": f"asset-item-{i}",
                "file_path": f"static/file_{i}.css",
                "content_type": "text/css",
                "size_bytes": 10,
                "sri_hash": "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=",
            }
            for i in range(501)
        ],
    }
    with pytest.raises(AssetContractViolationError) as exc_info:
        validate_asset_manifest(manifest_data)
    assert exc_info.value.code == "ERR_ASSET_CAPACITY_EXCEEDED"
