"""Incremental Markdown AST Table of Contents & Anchor Slug Generator."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


@dataclass
class HeadingNode:
    """Represents a heading node in the hierarchical TOC tree."""
    level: int
    title: str
    slug: str
    children: List[HeadingNode] = field(default_factory=list)


def slugify_heading(title: str, seen_slugs: Optional[Set[str]] = None) -> str:
    """Converts a heading title into a clean, collision-free URL anchor slug.
    
    1. Normalizes unicode (NFKD) and strips non-ASCII where applicable.
    2. Strips Markdown formatting (links, bold, italics, inline code).
    3. Replaces whitespace and non-alphanumeric chars with hyphens.
    4. Handles duplicates by suffixing `-1`, `-2`, etc.
    """
    if not title:
        base = "section"
    else:
        # Strip inline markdown links: [text](url) -> text
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
        # Strip bold/italics
        clean = re.sub(r"[*_~`]", "", clean)
        # Normalize unicode
        clean = unicodedata.normalize("NFKD", clean)
        clean = clean.encode("ascii", "ignore").decode("ascii")
        # Lowercase and replace non-alphanumeric with hyphens
        clean = re.sub(r"[^\w\s-]", "", clean).strip().lower()
        base = re.sub(r"[-\s]+", "-", clean)
        if not base:
            base = "section"

    if seen_slugs is None:
        return base

    slug = base
    counter = 1
    while slug in seen_slugs:
        slug = f"{base}-{counter}"
        counter += 1

    seen_slugs.add(slug)
    return slug


def parse_markdown_headings(markdown_text: str) -> List[Tuple[int, str, str]]:
    """Extracts (level, raw_title, slug) from Markdown ATX headings.
    
    Defensively skips fenced code blocks and HTML comments.
    """
    if not markdown_text:
        return []

    lines = markdown_text.splitlines()
    in_code_block = False
    in_html_comment = False
    seen_slugs: Set[str] = set()
    headings: List[Tuple[int, str, str]] = []

    # Matches ATX headings: # Heading up to ###### Heading
    heading_regex = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?$")

    for line in lines:
        stripped = line.strip()

        # Handle fenced code blocks
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Handle multi-line HTML comments
        if "<!--" in stripped and "-->" not in stripped:
            in_html_comment = True
            continue
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue

        match = heading_regex.match(stripped)
        if match:
            level = len(match.group(1))
            raw_title = match.group(2).strip()
            # Clean title of inline code markers and links for plain display
            clean_display_title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw_title)
            clean_display_title = re.sub(r"[*_~`]", "", clean_display_title).strip()
            slug = slugify_heading(raw_title, seen_slugs)
            headings.append((level, clean_display_title, slug))

    return headings


def build_heading_tree(headings: List[Tuple[int, str, str]]) -> List[HeadingNode]:
    """Builds a hierarchical tree from a flat list of (level, title, slug) tuples."""
    root_nodes: List[HeadingNode] = []
    # Stack stores (node, level)
    stack: List[HeadingNode] = []

    for level, title, slug in headings:
        node = HeadingNode(level=level, title=title, slug=slug)

        while stack and stack[-1].level >= level:
            stack.pop()

        if not stack:
            root_nodes.append(node)
        else:
            stack[-1].children.append(node)

        stack.append(node)

    return root_nodes


def render_markdown_toc(
    nodes: List[HeadingNode],
    min_level: int = 1,
    max_level: int = 6,
    indent_spaces: int = 2,
    ordered: bool = False,
    current_depth: int = 0
) -> str:
    """Renders a heading tree into Markdown list format."""
    lines: List[str] = []

    for i, node in enumerate(nodes, 1):
        if min_level <= node.level <= max_level:
            prefix = " " * (current_depth * indent_spaces)
            bullet = f"{i}." if ordered else "-"
            lines.append(f"{prefix}{bullet} [{node.title}](#{node.slug})")
            next_depth = current_depth + 1
        else:
            next_depth = current_depth

        if node.children:
            sub = render_markdown_toc(
                node.children,
                min_level=min_level,
                max_level=max_level,
                indent_spaces=indent_spaces,
                ordered=ordered,
                current_depth=next_depth
            )
            if sub:
                lines.append(sub)

    return "\n".join(lines)


def render_html_toc(
    nodes: List[HeadingNode],
    min_level: int = 1,
    max_level: int = 6,
    nav_class: str = "toc",
    ordered: bool = False
) -> str:
    """Renders a heading tree into semantic HTML <nav> with <ul> or <ol>."""
    tag = "ol" if ordered else "ul"

    def _render_list(children: List[HeadingNode]) -> str:
        items: List[str] = []
        for node in children:
            if not (min_level <= node.level <= max_level):
                # If current node is outside level bounds, still check children
                if node.children:
                    sub = _render_list(node.children)
                    if sub:
                        items.append(sub)
                continue

            child_html = ""
            if node.children:
                child_sub = _render_list(node.children)
                if child_sub:
                    child_html = f"\n{child_sub}\n"

            items.append(f'<li><a href="#{node.slug}">{node.title}</a>{child_html}</li>')

        if not items:
            return ""
        joined = "\n".join(items)
        return f"<{tag}>\n{joined}\n</{tag}>"

    inner = _render_list(nodes)
    if not inner:
        return ""

    return f'<nav class="{nav_class}">\n{inner}\n</nav>'


def extract_table_of_contents(
    markdown_text: str,
    min_level: int = 2,
    max_level: int = 4,
    ordered: bool = False
) -> dict:
    """High-level generator returning structured metadata, Markdown, and HTML TOC."""
    headings = parse_markdown_headings(markdown_text)
    tree = build_heading_tree(headings)
    md_toc = render_markdown_toc(tree, min_level=min_level, max_level=max_level, ordered=ordered)
    html_toc = render_html_toc(tree, min_level=min_level, max_level=max_level, ordered=ordered)

    return {
        "count": len(headings),
        "headings": [{"level": h[0], "title": h[1], "slug": h[2]} for h in headings],
        "markdown": md_toc,
        "html": html_toc,
    }
