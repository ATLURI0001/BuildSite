"""
Unit tests for BuildSite Incremental Route Tree and Cache-Control Policy Matrix.
"""

import pytest
from buildsite.route_tree import RouteTree, RoutePolicy, CACHE_CONTROL_DIRECTIVES


def test_route_tree_exact_match():
    tree = RouteTree()
    tree.register("/docs", "docs_handler", RoutePolicy.SSG_HTML)
    tree.register("/docs/setup", "setup_handler", RoutePolicy.SSG_HTML)
    tree.register("/api/v1/health", "health_handler", RoutePolicy.DYNAMIC_API)

    m1 = tree.match("/docs")
    assert m1 is not None
    assert m1.handler_id == "docs_handler"
    assert m1.policy == RoutePolicy.SSG_HTML
    assert m1.cache_control == CACHE_CONTROL_DIRECTIVES[RoutePolicy.SSG_HTML]

    m2 = tree.match("/api/v1/health")
    assert m2 is not None
    assert m2.handler_id == "health_handler"
    assert m2.policy == RoutePolicy.DYNAMIC_API
    assert "no-store" in m2.cache_control

    assert tree.match("/docs/nonexistent") is None


def test_route_tree_precedence_hierarchy():
    tree = RouteTree()
    # Register overlapping patterns: exact, param, and wildcard
    tree.register("/posts/featured", "featured_handler", RoutePolicy.SSG_HTML)
    tree.register("/posts/:id", "post_detail_handler", RoutePolicy.ISR_REVALIDATE)
    tree.register("/posts/*rest", "wildcard_handler", RoutePolicy.DYNAMIC_API)

    # 1. Exact match takes precedence over :id
    m_exact = tree.match("/posts/featured")
    assert m_exact is not None
    assert m_exact.handler_id == "featured_handler"
    assert m_exact.params == {}

    # 2. Dynamic param takes precedence over wildcard for single segment
    m_param = tree.match("/posts/12345")
    assert m_param is not None
    assert m_param.handler_id == "post_detail_handler"
    assert m_param.params == {"id": "12345"}
    assert m_param.policy == RoutePolicy.ISR_REVALIDATE

    # 3. Wildcard catches deep paths
    m_wild = tree.match("/posts/archive/2026/november")
    assert m_wild is not None
    assert m_wild.handler_id == "wildcard_handler"
    assert m_wild.params == {"rest": "archive/2026/november"}


def test_route_tree_cache_control_and_static_asset():
    tree = RouteTree()
    tree.register(
        "/static/*file",
        "asset_handler",
        RoutePolicy.STATIC_ASSET,
        custom_cache_control=None,
    )

    m = tree.match("/static/css/main.8a7b9c.css")
    assert m is not None
    assert m.policy == RoutePolicy.STATIC_ASSET
    assert "immutable" in m.cache_control
    assert "max-age=31536000" in m.cache_control
    assert m.params == {"file": "css/main.8a7b9c.css"}


def test_route_tree_path_traversal_defense():
    tree = RouteTree()
    tree.register("/assets/*file", "assets", RoutePolicy.STATIC_ASSET)

    # Path traversal should be rejected with None match
    assert tree.match("/assets/../secret.env") is None
    assert tree.match("/assets/%2e%2e/passwd") is None


def test_route_tree_normalization():
    tree = RouteTree()
    tree.register("blog//announcement/", "blog_announcement")

    # Matching with query params, hash, and trailing slashes
    m = tree.match("/blog/announcement?utm_source=twitter#overview")
    assert m is not None
    assert m.handler_id == "blog_announcement"
