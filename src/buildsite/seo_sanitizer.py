"""HTML OpenGraph SEO meta tag generator, slug normalizer, and sitemap XML builder."""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

_SLUG_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_WHITESPACE_COLLAPSE = re.compile(r"\s+")


def sanitize_slug(text: str, max_length: int = 80) -> str:
    """Normalize arbitrary UTF-8 text into a safe, deterministic, URL-friendly kebab-case slug.

    Performs Unicode NFKD decomposition, strips combining diacritical marks,
    converts to lowercase, collapses non-alphanumeric runes into single hyphens,
    and strips leading/trailing hyphens.
    """
    if not text or not isinstance(text, str):
        return "untitled"

    # NFKD decomposition separates base letters from accents
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_bytes = decomposed.encode("ascii", "ignore")
    cleaned = ascii_bytes.decode("ascii").lower().strip()

    # Replace non-alphanumeric with hyphen
    slug = _SLUG_NON_ALPHANUMERIC.sub("-", cleaned).strip("-")

    if not slug:
        return "untitled"

    if len(slug) > max_length:
        # Avoid splitting words mid-hyphen if possible
        truncated = slug[:max_length].rstrip("-")
        return truncated if truncated else slug[:max_length]

    return slug


def validate_canonical_url(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
    """Validate canonical URL syntax, ensuring HTTPS scheme and optional domain whitelisting."""
    if not url or not isinstance(url, str):
        return False

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return False

    if allowed_domains:
        netloc = parsed.netloc.lower()
        # Allow exact match or subdomain match
        matched = any(netloc == d.lower() or netloc.endswith("." + d.lower()) for d in allowed_domains)
        if not matched:
            return False

    return True


@dataclass
class OpenGraphMeta:
    title: str
    description: str
    canonical_url: str
    image_url: Optional[str] = None
    site_name: str = "BuildSite"
    card_type: str = "summary_large_image"

    def render_meta_tags(self) -> str:
        """Render hardened HTML OpenGraph and Twitter card <meta> tags, escaping all attributes."""
        safe_title = html.escape(self.title.strip(), quote=True)
        safe_desc = html.escape(self.description.strip(), quote=True)
        safe_url = html.escape(self.canonical_url.strip(), quote=True)
        safe_site = html.escape(self.site_name.strip(), quote=True)
        safe_card = html.escape(self.card_type.strip(), quote=True)

        lines = [
            f'<meta property="og:title" content="{safe_title}">',
            f'<meta property="og:description" content="{safe_desc}">',
            f'<meta property="og:url" content="{safe_url}">',
            f'<meta property="og:site_name" content="{safe_site}">',
            '<meta property="og:type" content="website">',
            f'<meta name="twitter:card" content="{safe_card}">',
            f'<meta name="twitter:title" content="{safe_title}">',
            f'<meta name="twitter:description" content="{safe_desc}">',
        ]

        if self.image_url and self.image_url.strip():
            safe_img = html.escape(self.image_url.strip(), quote=True)
            lines.append(f'<meta property="og:image" content="{safe_img}">')
            lines.append(f'<meta name="twitter:image" content="{safe_img}">')

        return "\n".join(lines)


def build_sitemap_xml_entry(loc: str, lastmod: str, changefreq: str = "weekly", priority: float = 0.8) -> str:
    """Construct a compliant W3C XML <url> element for sitemap.xml with sanitized fields."""
    safe_loc = html.escape(loc.strip(), quote=True)
    safe_lastmod = html.escape(lastmod.strip(), quote=True)

    allowed_freqs = {"always", "hourly", "daily", "weekly", "monthly", "yearly", "never"}
    clean_freq = changefreq.lower().strip()
    if clean_freq not in allowed_freqs:
        clean_freq = "weekly"

    # Clamp priority to [0.0, 1.0]
    safe_priority = max(0.0, min(1.0, float(priority)))

    return (
        f"  <url>\n"
        f"    <loc>{safe_loc}</loc>\n"
        f"    <lastmod>{safe_lastmod}</lastmod>\n"
        f"    <changefreq>{clean_freq}</changefreq>\n"
        f"    <priority>{safe_priority:.1f}</priority>\n"
        f"  </url>"
    )
