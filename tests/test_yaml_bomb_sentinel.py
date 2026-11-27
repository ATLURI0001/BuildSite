"""Tests for yaml_bomb_sentinel."""
import pytest
from buildsite.yaml_bomb_sentinel import assert_safe_yaml_size


def test_yaml_bomb_sentinel():
    assert_safe_yaml_size("title: Hello\n")
    with pytest.raises(ValueError):
        assert_safe_yaml_size("&a " * 40)
