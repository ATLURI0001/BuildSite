"""Unit tests for SiteEnvironmentContract and configuration sanitization routines."""

from __future__ import annotations

import pytest
from buildsite.env_contract import (
    ContractValidationError,
    SiteEnvironmentContract,
    parse_bool_flag,
    sanitize_environment_name,
    sanitize_path_segment,
    sanitize_port,
    sanitize_site_url,
)


def test_parse_bool_flag_truthy_and_falsy() -> None:
    for truthy in ("1", "true", "TRUE", "True", "yes", "YES", "on", "enable", "enabled", True, 1):
        assert parse_bool_flag(truthy) is True

    for falsy in ("0", "false", "FALSE", "False", "no", "NO", "off", "disable", "disabled", "", False, 0):
        assert parse_bool_flag(falsy) is False

    assert parse_bool_flag(None, default=True) is True
    assert parse_bool_flag(None, default=False) is False

    with pytest.raises(ContractValidationError, match="Invalid boolean flag"):
        parse_bool_flag("maybe")

    with pytest.raises(ContractValidationError, match="Invalid boolean flag type"):
        parse_bool_flag([1, 2, 3])


def test_sanitize_site_url_valid_and_normalization() -> None:
    assert sanitize_site_url("https://example.com/") == "https://example.com"
    assert sanitize_site_url("http://localhost:3000/docs/") == "http://localhost:3000/docs"
    assert sanitize_site_url("https://example.com:443") == "https://example.com"
    assert sanitize_site_url(None) == "https://localhost:8000"


def test_sanitize_site_url_rejections() -> None:
    # Prohibit non-http/https schemes
    with pytest.raises(ContractValidationError, match="Invalid URL scheme"):
        sanitize_site_url("ftp://example.com/site")

    # Prohibit embedded credentials
    with pytest.raises(ContractValidationError, match="embedded user credentials"):
        sanitize_site_url("https://user:password@example.com")

    # Prohibit control characters
    with pytest.raises(ContractValidationError, match="control characters"):
        sanitize_site_url("https://example.com/\x00evil")


def test_sanitize_port_bounds_and_privileged() -> None:
    assert sanitize_port("8080") == 8080
    assert sanitize_port(3000) == 3000
    assert sanitize_port(None, default=9000) == 9000

    # Privileged port rejection
    with pytest.raises(ContractValidationError, match="Privileged port"):
        sanitize_port(80, allow_privileged=False)

    assert sanitize_port(80, allow_privileged=True) == 80

    # Out of range
    with pytest.raises(ContractValidationError, match="outside allowed TCP range"):
        sanitize_port(0)
    with pytest.raises(ContractValidationError, match="outside allowed TCP range"):
        sanitize_port(70000)

    # Malformed integer
    with pytest.raises(ContractValidationError, match="not a valid integer"):
        sanitize_port("invalid-port")


def test_sanitize_environment_name() -> None:
    assert sanitize_environment_name("PRODUCTION") == "production"
    assert sanitize_environment_name("Staging") == "staging"
    assert sanitize_environment_name("development") == "development"
    assert sanitize_environment_name("testing") == "testing"
    assert sanitize_environment_name(None) == "development"

    with pytest.raises(ContractValidationError, match="Invalid environment"):
        sanitize_environment_name("local-cluster")


def test_sanitize_path_segment_traversal_defense() -> None:
    assert sanitize_path_segment("build/public") == "build/public"
    assert sanitize_path_segment(None, default="dist") == "dist"

    with pytest.raises(ContractValidationError, match="Path traversal"):
        sanitize_path_segment("../secret_dir")

    with pytest.raises(ContractValidationError, match="Path traversal"):
        sanitize_path_segment("build/../../etc")

    with pytest.raises(ContractValidationError, match="Absolute filesystem paths"):
        sanitize_path_segment("/var/www/html")

    with pytest.raises(ContractValidationError, match="control characters"):
        sanitize_path_segment("dist/\x00null")


def test_site_environment_contract_from_dict() -> None:
    env_mock = {
        "BUILDSITE_URL": "https://docs.acme.org",
        "BUILDSITE_PORT": "8443",
        "BUILDSITE_ENV": "production",
        "BUILDSITE_DEBUG": "false",
        "BUILDSITE_ENABLE_SITEMAP": "true",
        "BUILDSITE_ENABLE_RSS": "0",
        "BUILDSITE_OUTPUT_DIR": "site_build",
        "BUILDSITE_API_KEY": "ak_live_9876543210abcdef",
    }

    contract = SiteEnvironmentContract.from_env(env_mock)
    assert contract.site_url == "https://docs.acme.org"
    assert contract.port == 8443
    assert contract.environment == "production"
    assert contract.debug is False
    assert contract.enable_sitemap is True
    assert contract.enable_rss is False
    assert contract.output_dir == "site_build"
    assert contract.has_api_key is True
    assert contract.api_key_masked == "ak_l...cdef"

    safe_dict = contract.to_safe_dict()
    assert "ak_live_9876543210abcdef" not in str(safe_dict)
    assert safe_dict["api_key"] == "ak_l...cdef"
