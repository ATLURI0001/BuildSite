"""Unit tests for Markdown AST Table of Contents & Anchor Slug Generator."""

import pytest
from buildsite.toc_generator import (
    slugify_heading,
    parse_markdown_headings,
    build_heading_tree,
    render_markdown_toc,
    render_html_toc,
    extract_table_of_contents,
)


def test_slugify_heading_basics_and_unicode():
    assert slugify_heading("Introduction to Architecture") == "introduction-to-architecture"
    assert slugify_heading("API Reference: v2.0 (Stable!)") == "api-reference-v20-stable"
    # Strips markdown links and formatting
    assert slugify_heading("Deploying with [Docker](https://docker.com)") == "deploying-with-docker"
    assert slugify_heading("Using `asyncio` & **Multiprocessing**") == "using-asyncio-multiprocessing"
    # Unicode accent normalization
    assert slugify_heading("Café & Resumé Guide") == "cafe-resume-guide"
    # Fallback for empty
    assert slugify_heading("") == "section"


def test_slugify_heading_collision_disambiguation():
    seen = set()
    s1 = slugify_heading("Overview", seen)
    s2 = slugify_heading("Overview", seen)
    s3 = slugify_heading("Overview", seen)

    assert s1 == "overview"
    assert s2 == "overview-1"
    assert s3 == "overview-2"


def test_parse_markdown_headings_atx_and_fences():
    doc = """
# Main Title
Introductory text.

```python
# This is a python comment, not a heading
def foo():
    pass
```

## Section 1: Setup ##
Some setup notes.

~~~bash
### Not a heading either
echo "hello"
~~~

<!--
### Commented out heading
-->

### Subsection A
Details here.

#### Deep Leaf
Leaf details.
"""
    headings = parse_markdown_headings(doc)

    assert len(headings) == 4
    assert headings[0] == (1, "Main Title", "main-title")
    assert headings[1] == (2, "Section 1: Setup", "section-1-setup")
    assert headings[2] == (3, "Subsection A", "subsection-a")
    assert headings[3] == (4, "Deep Leaf", "deep-leaf")


def test_build_heading_tree_hierarchy():
    flat = [
        (1, "Top Level 1", "top-1"),
        (2, "Sub 1.1", "sub-1-1"),
        (3, "Sub 1.1.1", "sub-1-1-1"),
        (2, "Sub 1.2", "sub-1-2"),
        (1, "Top Level 2", "top-2"),
    ]
    tree = build_heading_tree(flat)

    assert len(tree) == 2
    assert tree[0].title == "Top Level 1"
    assert len(tree[0].children) == 2
    assert tree[0].children[0].title == "Sub 1.1"
    assert len(tree[0].children[0].children) == 1
    assert tree[0].children[0].children[0].title == "Sub 1.1.1"
    assert tree[0].children[1].title == "Sub 1.2"
    assert tree[1].title == "Top Level 2"
    assert len(tree[1].children) == 0


def test_render_markdown_toc_formatting():
    flat = [
        (1, "Document Title", "doc-title"),
        (2, "Quickstart", "quickstart"),
        (3, "Installation", "installation"),
        (2, "Configuration", "configuration"),
    ]
    tree = build_heading_tree(flat)

    # Filter out H1 (min_level=2)
    md = render_markdown_toc(tree, min_level=2, max_level=3, indent_spaces=2)
    lines = md.splitlines()

    assert len(lines) == 3
    assert lines[0] == "- [Quickstart](#quickstart)"
    assert lines[1] == "  - [Installation](#installation)"
    assert lines[2] == "- [Configuration](#configuration)"

    # Ordered list
    ordered_md = render_markdown_toc(tree, min_level=2, max_level=3, ordered=True)
    assert "1. [Quickstart](#quickstart)" in ordered_md
    assert "2. [Configuration](#configuration)" in ordered_md


def test_render_html_toc_semantic_nav():
    flat = [
        (2, "Overview", "overview"),
        (3, "Metrics", "metrics"),
    ]
    tree = build_heading_tree(flat)
    html = render_html_toc(tree, min_level=2, max_level=3, nav_class="site-toc")

    assert '<nav class="site-toc">' in html
    assert '<li><a href="#overview">Overview</a>' in html
    assert '<li><a href="#metrics">Metrics</a></li>' in html


def test_extract_table_of_contents_end_to_end():
    doc = """
# System Specification

## Architecture
Overview of components.

### Pipeline
Dataflow stream.

### Storage
Persistent layer.

## Performance
Benchmarks.
"""
    toc = extract_table_of_contents(doc, min_level=2, max_level=3)

    assert toc["count"] == 5
    assert "- [Architecture](#architecture)" in toc["markdown"]
    assert "  - [Pipeline](#pipeline)" in toc["markdown"]
    assert "- [Performance](#performance)" in toc["markdown"]
    assert '<a href="#pipeline">Pipeline</a>' in toc["html"]
