"""
Unit tests for Navigation Hierarchy & Route Tree Boundary Contract.
"""

import pytest

from buildsite.navigation_hierarchy_contract import (
    NavigationHierarchyContract,
    NavigationNodeContract,
    NavigationContractViolationError,
    DuplicateNavIdError,
    DuplicateRouteHrefError,
    MaxDepthExceededError,
    CyclicNavigationError,
    InvalidRoutePathError,
)


def test_nominal_navigation_hierarchy():
    contract = NavigationHierarchyContract(max_depth=4)
    raw = [
        {
            "id": "docs",
            "title": "Documentation",
            "href": "/docs",
            "order": 1,
            "children": [
                {
                    "id": "docs-intro",
                    "title": "Introduction",
                    "href": "/docs/intro",
                    "order": 1,
                    "badge": "New",
                },
                {
                    "id": "docs-api",
                    "title": "API Reference",
                    "href": "/docs/api",
                    "order": 2,
                    "children": [
                        {
                            "id": "docs-api-v1",
                            "title": "v1 Endpoints",
                            "href": "/docs/api/v1",
                            "order": 1,
                        }
                    ],
                },
            ],
        },
        {
            "id": "home",
            "title": "Home",
            "href": "/",
            "order": 0,
        },
    ]

    roots = contract.validate_hierarchy(raw)
    assert len(roots) == 2
    # Sorted by order: home (0) then docs (1)
    assert roots[0].id == "home"
    assert roots[1].id == "docs"
    assert len(roots[1].children) == 2
    assert roots[1].children[0].id == "docs-intro"
    assert roots[1].children[0].badge == "New"

    # Breadcrumb resolution
    crumbs = contract.resolve_breadcrumbs("/docs/api/v1")
    assert crumbs is not None
    assert [c.id for c in crumbs] == ["docs", "docs-api", "docs-api-v1"]

    # Trailing slash normalization
    crumbs_slash = contract.resolve_breadcrumbs("/docs/api/v1/")
    assert crumbs_slash is not None
    assert len(crumbs_slash) == 3

    # Unknown route breadcrumb
    assert contract.resolve_breadcrumbs("/non-existent") is None

    # Flattening
    flat = contract.flatten()
    assert len(flat) == 5

    # Manifest
    manifest = contract.export_manifest()
    assert manifest["total_nodes"] == 5
    assert manifest["root_nodes"] == 2


def test_depth_boundary_enforcement():
    contract = NavigationHierarchyContract(max_depth=2)
    raw = [
        {
            "id": "lvl1",
            "title": "Level 1",
            "href": "/l1",
            "children": [
                {
                    "id": "lvl2",
                    "title": "Level 2",
                    "href": "/l1/l2",
                    "children": [
                        {
                            "id": "lvl3",
                            "title": "Level 3",
                            "href": "/l1/l2/l3",
                        }
                    ],
                }
            ],
        }
    ]

    with pytest.raises(MaxDepthExceededError) as exc_info:
        contract.validate_hierarchy(raw)
    assert "exceeds maximum allowable depth 2" in str(exc_info.value)


def test_duplicate_nav_id_detection():
    contract = NavigationHierarchyContract()
    raw = [
        {"id": "duplicate-id", "title": "First", "href": "/first"},
        {"id": "duplicate-id", "title": "Second", "href": "/second"},
    ]
    with pytest.raises(DuplicateNavIdError) as exc_info:
        contract.validate_hierarchy(raw)
    assert "duplicate-id" in str(exc_info.value)


def test_duplicate_href_detection():
    contract = NavigationHierarchyContract()
    raw = [
        {"id": "node-1", "title": "Overview", "href": "/guides"},
        {"id": "node-2", "title": "Guide Index", "href": "/guides/"},
    ]
    with pytest.raises(DuplicateRouteHrefError) as exc_info:
        contract.validate_hierarchy(raw)
    assert "/guides" in str(exc_info.value)


def test_invalid_href_path_traversal():
    contract = NavigationHierarchyContract()
    raw = [{"id": "bad-href", "title": "Exploit", "href": "/docs/../../etc/passwd"}]
    with pytest.raises(InvalidRoutePathError):
        contract.validate_hierarchy(raw)


def test_invalid_href_control_characters():
    contract = NavigationHierarchyContract()
    raw = [{"id": "bad-ctrl", "title": "Control", "href": "/docs/\x00null"}]
    with pytest.raises(InvalidRoutePathError):
        contract.validate_hierarchy(raw)


def test_relative_href_rejection():
    contract = NavigationHierarchyContract()
    raw = [{"id": "bad-rel", "title": "Relative", "href": "docs/page"}]
    with pytest.raises(InvalidRoutePathError):
        contract.validate_hierarchy(raw)


def test_external_link_policy():
    contract_allowed = NavigationHierarchyContract(allow_external_links=True)
    raw = [{"id": "github", "title": "GitHub Repo", "href": "https://github.com/ATLURI0001/buildsite"}]
    roots = contract_allowed.validate_hierarchy(raw)
    assert len(roots) == 1

    contract_forbidden = NavigationHierarchyContract(allow_external_links=False)
    with pytest.raises(NavigationContractViolationError):
        contract_forbidden.validate_hierarchy(raw)


def test_invalid_node_id_characters():
    contract = NavigationHierarchyContract()
    raw = [{"id": "bad id with spaces!", "title": "Bad ID", "href": "/bad"}]
    with pytest.raises(NavigationContractViolationError):
        contract.validate_hierarchy(raw)


def test_title_and_badge_boundaries():
    contract = NavigationHierarchyContract(max_title_length=10)
    raw = [{"id": "long-title", "title": "This title is way too long for the contract", "href": "/test"}]
    with pytest.raises(NavigationContractViolationError):
        contract.validate_hierarchy(raw)

    contract_normal = NavigationHierarchyContract()
    raw_badge = [{"id": "badge-test", "title": "Test", "href": "/test", "badge": "ExtremelyLongBadgeExceedingBoundary"}]
    with pytest.raises(NavigationContractViolationError):
        contract_normal.validate_hierarchy(raw_badge)


def test_hidden_nodes_filtering():
    contract = NavigationHierarchyContract()
    raw = [
        {"id": "public", "title": "Public", "href": "/public"},
        {"id": "internal", "title": "Internal", "href": "/internal", "hidden": True},
    ]
    contract.validate_hierarchy(raw)
    visible_flat = contract.flatten(include_hidden=False)
    assert len(visible_flat) == 1
    assert visible_flat[0].id == "public"

    all_flat = contract.flatten(include_hidden=True)
    assert len(all_flat) == 2
