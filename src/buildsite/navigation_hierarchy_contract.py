"""
Navigation Hierarchy & Route Tree Boundary Contract for buildsite.

Provides schema validation, acyclicity invariants, depth restrictions,
and path uniqueness verification across documentation and site navigation trees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class NavigationContractViolationError(ValueError):
    """Raised when a navigation tree violates structural or schema contracts."""
    pass


class DuplicateNavIdError(NavigationContractViolationError):
    """Raised when duplicate node IDs are detected in the navigation hierarchy."""
    pass


class DuplicateRouteHrefError(NavigationContractViolationError):
    """Raised when duplicate internal route paths are declared in navigation."""
    pass


class MaxDepthExceededError(NavigationContractViolationError):
    """Raised when navigation nesting depth exceeds the strict boundary."""
    pass


class CyclicNavigationError(NavigationContractViolationError):
    """Raised when cyclic references are detected in navigation hierarchies."""
    pass


class InvalidRoutePathError(NavigationContractViolationError):
    """Raised when a route href contains path traversal or invalid characters."""
    pass


ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class NavigationNodeContract:
    """Represents a validated immutable navigation node."""
    id: str
    title: str
    href: str
    order: int = 0
    children: List[NavigationNodeContract] = field(default_factory=list)
    badge: Optional[str] = None
    hidden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize node to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "href": self.href,
            "order": self.order,
            "children": [c.to_dict() for c in self.children],
            "badge": self.badge,
            "hidden": self.hidden,
        }


class NavigationHierarchyContract:
    """Enforces boundary conditions and structural invariants on navigation trees."""

    def __init__(
        self,
        max_depth: int = 5,
        max_title_length: int = 128,
        max_id_length: int = 64,
        allow_external_links: bool = True,
    ):
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        self.max_depth = max_depth
        self.max_title_length = max_title_length
        self.max_id_length = max_id_length
        self.allow_external_links = allow_external_links
        self._validated_roots: List[NavigationNodeContract] = []
        self._id_registry: Set[str] = set()
        self._href_registry: Set[str] = set()

    def validate_node_dict(self, raw: Dict[str, Any], current_depth: int, path_stack: List[str]) -> NavigationNodeContract:
        """Validate an individual node dictionary and its descendants."""
        if current_depth > self.max_depth:
            raise MaxDepthExceededError(
                f"Navigation depth {current_depth} exceeds maximum allowable depth {self.max_depth} at path {' -> '.join(path_stack)}"
            )

        # 1. Validate ID
        node_id = raw.get("id")
        if not node_id or not isinstance(node_id, str):
            raise NavigationContractViolationError(f"Node id must be a non-empty string, got: {node_id}")
        node_id = node_id.strip()
        if len(node_id) > self.max_id_length or not ID_REGEX.match(node_id):
            raise NavigationContractViolationError(
                f"Node id '{node_id}' is invalid. Must match ^[a-zA-Z0-9_-]+$ and be <= {self.max_id_length} chars."
            )
        if node_id in self._id_registry:
            raise DuplicateNavIdError(f"Duplicate navigation node id detected: '{node_id}'")
        self._id_registry.add(node_id)

        # Check for cycles via path_stack
        if node_id in path_stack:
            cycle_desc = " -> ".join(path_stack + [node_id])
            raise CyclicNavigationError(f"Cyclic navigation reference detected: {cycle_desc}")

        # 2. Validate Title
        title = raw.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            raise NavigationContractViolationError(f"Node '{node_id}' must have a non-empty title")
        title = title.strip()
        if len(title) > self.max_title_length:
            raise NavigationContractViolationError(
                f"Node '{node_id}' title exceeds max length of {self.max_title_length} characters"
            )

        # 3. Validate Href
        href = raw.get("href")
        if not href or not isinstance(href, str) or not href.strip():
            raise NavigationContractViolationError(f"Node '{node_id}' must have a non-empty href")
        href = href.strip()

        if CONTROL_CHARS_REGEX.search(href):
            raise InvalidRoutePathError(f"Node '{node_id}' href contains illegal control characters")
        if ".." in href or "//" in href.replace("https://", "").replace("http://", ""):
            raise InvalidRoutePathError(f"Node '{node_id}' href contains path traversal or invalid sequences: '{href}'")

        is_external = href.startswith("http://") or href.startswith("https://")
        if is_external and not self.allow_external_links:
            raise NavigationContractViolationError(f"External URLs are not permitted by contract: '{href}'")
        if not is_external and not href.startswith("/"):
            raise InvalidRoutePathError(f"Internal route href must be an absolute path starting with '/': '{href}'")

        # Uniqueness of internal routes
        if not is_external:
            norm_href = href.rstrip("/") or "/"
            if norm_href in self._href_registry:
                raise DuplicateRouteHrefError(f"Duplicate internal route href detected: '{norm_href}' (in node '{node_id}')")
            self._href_registry.add(norm_href)

        # 4. Validate Order
        order = raw.get("order", 0)
        if not isinstance(order, int) or order < 0:
            raise NavigationContractViolationError(f"Node '{node_id}' order must be a non-negative integer, got: {order}")

        # 5. Validate Badge
        badge = raw.get("badge")
        if badge is not None:
            if not isinstance(badge, str) or len(badge) > 24:
                raise NavigationContractViolationError(f"Node '{node_id}' badge must be a string <= 24 chars, got: {badge}")

        # 6. Validate Hidden
        hidden = bool(raw.get("hidden", False))

        # 7. Validate Children recursively
        raw_children = raw.get("children", [])
        if not isinstance(raw_children, list):
            raise NavigationContractViolationError(f"Node '{node_id}' children must be a list")

        validated_children: List[NavigationNodeContract] = []
        new_stack = path_stack + [node_id]
        for child_raw in raw_children:
            if not isinstance(child_raw, dict):
                raise NavigationContractViolationError(f"Child in '{node_id}' must be a dictionary")
            child_node = self.validate_node_dict(child_raw, current_depth + 1, new_stack)
            validated_children.append(child_node)

        # Sort children by order, then title
        validated_children.sort(key=lambda c: (c.order, c.title))

        return NavigationNodeContract(
            id=node_id,
            title=title,
            href=href,
            order=order,
            children=validated_children,
            badge=badge,
            hidden=hidden,
        )

    def validate_hierarchy(self, items: List[Dict[str, Any]]) -> List[NavigationNodeContract]:
        """Validate an entire navigation tree from raw specification dictionaries."""
        self._id_registry.clear()
        self._href_registry.clear()
        self._validated_roots = []

        if not isinstance(items, list):
            raise NavigationContractViolationError("Navigation specification must be a list of root node dictionaries")

        for raw_root in items:
            if not isinstance(raw_root, dict):
                raise NavigationContractViolationError("Root navigation item must be a dictionary")
            validated = self.validate_node_dict(raw_root, current_depth=1, path_stack=[])
            self._validated_roots.append(validated)

        self._validated_roots.sort(key=lambda r: (r.order, r.title))
        return self._validated_roots

    def resolve_breadcrumbs(self, target_href: str) -> Optional[List[NavigationNodeContract]]:
        """Resolve ordered ancestor breadcrumbs for a given target href path."""
        norm_target = target_href.rstrip("/") or "/"

        def _search(node: NavigationNodeContract, current_trail: List[NavigationNodeContract]) -> Optional[List[NavigationNodeContract]]:
            trail = current_trail + [node]
            node_norm = node.href.rstrip("/") or "/"
            if node_norm == norm_target:
                return trail
            for child in node.children:
                found = _search(child, trail)
                if found is not None:
                    return found
            return None

        for root in self._validated_roots:
            result = _search(root, [])
            if result is not None:
                return result
        return None

    def flatten(self, include_hidden: bool = False) -> List[NavigationNodeContract]:
        """Flatten the validated hierarchy into a depth-first ordered list."""
        result: List[NavigationNodeContract] = []

        def _collect(node: NavigationNodeContract):
            if not node.hidden or include_hidden:
                result.append(node)
                for child in node.children:
                    _collect(child)

        for root in self._validated_roots:
            _collect(root)
        return result

    def export_manifest(self) -> Dict[str, Any]:
        """Export validated navigation hierarchy manifest with metrics."""
        flat = self.flatten(include_hidden=True)
        return {
            "total_nodes": len(flat),
            "visible_nodes": len([n for n in flat if not n.hidden]),
            "root_nodes": len(self._validated_roots),
            "max_configured_depth": self.max_depth,
            "tree": [r.to_dict() for r in self._validated_roots],
        }
