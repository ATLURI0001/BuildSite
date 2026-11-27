"""Tests for PageSizeRotary."""
from buildsite.page_size_rotary import PageSizeRotary


def test_page_size_rotary():
    r = PageSizeRotary(capacity=2)
    r.record(100)
    r.record(200)
    r.record(400)
    assert r.avg_bytes() == 300.0
