import pytest
from src.buildsite.asset_fingerprint_sentinel import validate_asset_fingerprint


def test_asset_fingerprint_sentinel():
    validate_asset_fingerprint("deadbeef")
    with pytest.raises(ValueError, match="invalid asset fingerprint"):
        validate_asset_fingerprint("not_a_hash!")
