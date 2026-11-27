"""Tests for page_render_rotary."""
import sys
sys.path.insert(0, "src")
from buildsite.page_render_rotary import PageRenderRotary


def test_page_render_rotary():
    r = PageRenderRotary(max_size=2)
    r.push("index.html"); r.push("about.html"); r.push("blog.html")
    assert r.count() == 2
