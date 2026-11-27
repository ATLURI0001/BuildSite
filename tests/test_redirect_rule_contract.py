"""Tests for redirect_rule_contract."""
import pytest
from buildsite.redirect_rule_contract import validate_redirect_rule


def test_redirect_rule_contract():
    validate_redirect_rule({"source": "/old", "destination": "/new"})
    with pytest.raises(ValueError):
        validate_redirect_rule({"source": "/loop", "destination": "/loop"})
