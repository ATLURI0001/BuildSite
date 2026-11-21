"""
BuildSite: Incremental Static Route Tree & Cache-Control Policy Matrix.
Implements a radix-trie routing tree with strict segment precedence and HTTP cache policy synthesis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class RoutePolicy(str, Enum):
    STATIC_ASSET = "static_asset"
    SSG_HTML = "ssg_html"
    DYNAMIC_API = "dynamic_api"
    ISR_REVALIDATE = "isr_revalidate"
    CUSTOM = "custom"


CACHE_CONTROL_DIRECTIVES: Dict[RoutePolicy, str] = {
    RoutePolicy.STATIC_ASSET: "public, max-age=31536000, immutable",
    RoutePolicy.SSG_HTML: "public, max-age=3600, s-maxage=86400, stale-while-revalidate=60",
    RoutePolicy.DYNAMIC_API: "no-cache, no-store, must-revalidate",
    RoutePolicy.ISR_REVALIDATE: "public, max-age=60, s-maxage=300, stale-if-error=86400",
}


@dataclass
class RouteMatch:
    route_pattern: str
    handler_id: str
    params: Dict[str, str] = field(default_factory=dict)
    policy: RoutePolicy = RoutePolicy.SSG_HTML
    cache_control: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class _RouteNode:
    def __init__(self, segment: str):
        self.segment = segment
        self.static_children: Dict[str, _RouteNode] = {}
        self.param_child: Optional[_RouteNode] = None
        self.param_name: Optional[str] = None
        self.wildcard_child: Optional[_RouteNode] = None
        self.wildcard_name: Optional[str] = None

        # Route endpoint data if this node terminates a registered pattern
        self.is_terminal: bool = False
        self.route_pattern: Optional[str] = None
        self.handler_id: Optional[str] = None
        self.policy: RoutePolicy = RoutePolicy.SSG_HTML
        self.custom_cache_control: Optional[str] = None
        self.metadata: Dict[str, Any] = {}


class RouteTree:
    """
    High-performance Trie router enforcing: Exact Match > Parameter Match > Wildcard Catch-all.
    """

    def __init__(self):
        self.root = _RouteNode("")
        self._route_count = 0

    @staticmethod
    def normalize_path(path: str) -> str:
        """Sanitizes incoming URL path, strips query/hash, normalizes slashes, and detects traversal."""
        if not path or not isinstance(path, str):
            return "/"

        # Strip query strings and fragment identifiers
        path = path.split("?")[0].split("#")[0].strip()

        # Check path traversal
        if ".." in path or "%2e%2e" in path.lower():
            raise ValueError(f"Path traversal detected in route: {path}")

        # Collapse consecutive slashes
        clean = re.sub(r"/+", "/", path)

        if not clean.startswith("/"):
            clean = "/" + clean

        # Normalize trailing slash (keep root as '/')
        if len(clean) > 1 and clean.endswith("/"):
            clean = clean[:-1]

        return clean

    def register(
        self,
        pattern: str,
        handler_id: str,
        policy: RoutePolicy = RoutePolicy.SSG_HTML,
        custom_cache_control: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registers a route pattern into the trie."""
        clean_pattern = self.normalize_path(pattern)
        if not handler_id:
            raise ValueError("handler_id cannot be empty")

        segments = [s for s in clean_pattern.split("/") if s]
        curr = self.root

        for seg in segments:
            if seg.startswith("*"):
                # Wildcard segment (e.g., *rest)
                w_name = seg[1:] or "wildcard"
                if curr.wildcard_child is None:
                    curr.wildcard_child = _RouteNode(seg)
                    curr.wildcard_name = w_name
                curr = curr.wildcard_child
                break  # Wildcard must be the terminal segment
            elif seg.startswith(":"):
                # Param segment (e.g., :id)
                p_name = seg[1:]
                if not p_name:
                    raise ValueError(f"Invalid dynamic param segment '{seg}'")
                if curr.param_child is None:
                    curr.param_child = _RouteNode(seg)
                    curr.param_name = p_name
                curr = curr.param_child
            else:
                # Static segment
                if seg not in curr.static_children:
                    curr.static_children[seg] = _RouteNode(seg)
                curr = curr.static_children[seg]

        curr.is_terminal = True
        curr.route_pattern = clean_pattern
        curr.handler_id = handler_id
        curr.policy = policy
        curr.custom_cache_control = custom_cache_control
        curr.metadata = metadata or {}
        self._route_count += 1

    def match(self, path: str) -> Optional[RouteMatch]:
        """Matches a request path against the trie respecting strict segment precedence."""
        try:
            clean_path = self.normalize_path(path)
        except ValueError:
            return None

        segments = [s for s in clean_path.split("/") if s]
        params: Dict[str, str] = {}

        def _traverse(node: _RouteNode, seg_idx: int) -> Optional[Tuple[_RouteNode, Dict[str, str]]]:
            # If all segments consumed
            if seg_idx == len(segments):
                if node.is_terminal:
                    return node, params.copy()
                # Check if this node has an empty-matching wildcard terminal
                if node.wildcard_child and node.wildcard_child.is_terminal:
                    p = params.copy()
                    p[node.wildcard_name or "wildcard"] = ""
                    return node.wildcard_child, p
                return None

            curr_seg = segments[seg_idx]

            # 1. Exact static match (highest precedence)
            if curr_seg in node.static_children:
                res = _traverse(node.static_children[curr_seg], seg_idx + 1)
                if res is not None:
                    return res

            # 2. Dynamic parameter match (middle precedence)
            if node.param_child:
                old_val = params.get(node.param_name)
                params[node.param_name] = curr_seg
                res = _traverse(node.param_child, seg_idx + 1)
                if res is not None:
                    return res
                # Backtrack
                if old_val is not None:
                    params[node.param_name] = old_val
                else:
                    params.pop(node.param_name, None)

            # 3. Wildcard catch-all match (lowest precedence)
            if node.wildcard_child and node.wildcard_child.is_terminal:
                remaining_path = "/".join(segments[seg_idx:])
                p = params.copy()
                p[node.wildcard_name or "wildcard"] = remaining_path
                return node.wildcard_child, p

            return None

        result = _traverse(self.root, 0)
        if result is None:
            return None

        matched_node, matched_params = result
        cache_hdr = matched_node.custom_cache_control or CACHE_CONTROL_DIRECTIVES.get(
            matched_node.policy, "no-cache"
        )

        return RouteMatch(
            route_pattern=matched_node.route_pattern or clean_path,
            handler_id=matched_node.handler_id or "",
            params=matched_params,
            policy=matched_node.policy,
            cache_control=cache_hdr,
            metadata=matched_node.metadata,
        )

    @property
    def route_count(self) -> int:
        return self._route_count
