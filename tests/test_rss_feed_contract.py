"""Tests for rss_feed_contract."""
import pytest
from buildsite.rss_feed_contract import validate_rss_item


def test_rss_feed_contract():
    validate_rss_item({"title": "Post", "link": "https://x.com/1", "pubDate": "2026-01-01"})
    with pytest.raises(ValueError):
        validate_rss_item({"title": "Post", "link": ""})
