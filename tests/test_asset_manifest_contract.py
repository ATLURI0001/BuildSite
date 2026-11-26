"""Tests for asset_manifest_contract."""
import pytest
from buildsite.asset_manifest_contract import validate_asset_entry


def test_asset_manifest_contract():
    validate_asset_entry({"path": "app.js", "size": 1024})
    with pytest.raises(ValueError):
        validate_asset_entry({"path": "", "size": -1})
