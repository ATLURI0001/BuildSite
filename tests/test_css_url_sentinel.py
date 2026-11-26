"""Tests for css_url_sentinel."""
import pytest
from buildsite.css_url_sentinel import assert_safe_css_url


def test_css_url_sentinel():
    assert_safe_css_url("background: url('/img/bg.png');")
    with pytest.raises(ValueError):
        assert_safe_css_url("background: url('javascript:alert(1)');")
