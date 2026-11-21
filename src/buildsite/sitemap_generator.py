"""
Sitemap Protocol Engine and XML Index Partitioner for BuildSite.
Enforces Sitemaps XML 0.9 protocol, W3C datetime standards, canonical URL sanitization,
and automatic multi-tier priority heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
import xml.etree.ElementTree as ET

VALID_CHANGEFREQS = {
    "always",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "never",
}

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
}


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None
    priority: Optional[float] = None


class SitemapGenerator:
    """
    Constructs, partitions, and renders XML sitemaps and sitemap indexes
    conforming strictly to sitemaps.org protocol schema 0.9.
    """

    def __init__(self, base_url: str, max_urls_per_sitemap: int = 50000):
        cleaned = base_url.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid base_url: must be a valid http or https URL, got '{base_url}'")

        self.base_url = cleaned
        self.max_urls_per_sitemap = max(1, max_urls_per_sitemap)
        self.entries: List[SitemapEntry] = []

    def sanitize_url(self, raw_path_or_url: str) -> str:
        """
        Resolves relative paths against base_url, strips tracking query parameters,
        normalizes trailing slashes, and verifies scheme.
        """
        trimmed = raw_path_or_url.strip()
        if not trimmed:
            raise ValueError("URL cannot be empty")

        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            full_url = trimmed
        else:
            rel = "/" + trimmed.lstrip("/")
            full_url = urljoin(self.base_url, rel)

        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid resolved URL: {full_url}")

        # Strip tracking query parameters
        if parsed.query:
            qs = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in qs.items() if k.lower() not in TRACKING_QUERY_PARAMS}
            clean_query = urlencode(filtered, doseq=True)
        else:
            clean_query = ""

        # Normalize path
        norm_path = re.sub(r"/+", "/", parsed.path)
        if not norm_path:
            norm_path = "/"

        reconstructed = urlunparse((
            parsed.scheme,
            parsed.netloc,
            norm_path,
            parsed.params,
            clean_query,
            ""  # Strip fragment
        ))
        return reconstructed

    @staticmethod
    def format_lastmod(val: Optional[date | datetime | str]) -> Optional[str]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(val, date):
            return val.strftime("%Y-%m-%d")
        if isinstance(val, str):
            clean = val.strip()
            # Verify YYYY-MM-DD or ISO 8601 format
            if re.match(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2}))?$", clean):
                return clean
            raise ValueError(f"Invalid lastmod datetime string: '{clean}'")
        raise TypeError(f"Unsupported lastmod type: {type(val)}")

    def calculate_depth_priority(self, path: str) -> float:
        """
        Derives search engine index priority based on URL path hierarchy depth:
        - Root (/) -> 1.0
        - Depth 1 (/docs) -> 0.8
        - Depth 2 (/docs/guide) -> 0.6
        - Depth 3+ (/docs/guide/advanced) -> 0.4
        """
        segments = [s for s in path.strip("/").split("/") if s]
        depth = len(segments)
        if depth == 0:
            return 1.0
        if depth == 1:
            return 0.8
        if depth == 2:
            return 0.6
        return 0.4

    def calculate_depth_changefreq(self, path: str) -> str:
        segments = [s for s in path.strip("/").split("/") if s]
        depth = len(segments)
        if depth == 0:
            return "daily"
        if depth == 1:
            return "weekly"
        return "monthly"

    def add_url(
        self,
        path_or_url: str,
        lastmod: Optional[date | datetime | str] = None,
        changefreq: Optional[str] = None,
        priority: Optional[float] = None,
    ) -> SitemapEntry:
        loc = self.sanitize_url(path_or_url)
        path = urlparse(loc).path

        if changefreq is not None:
            cf = changefreq.lower().strip()
            if cf not in VALID_CHANGEFREQS:
                raise ValueError(f"Invalid changefreq '{changefreq}'. Must be one of {sorted(VALID_CHANGEFREQS)}")
        else:
            cf = self.calculate_depth_changefreq(path)

        if priority is not None:
            if not (0.0 <= priority <= 1.0):
                raise ValueError(f"Priority must be between 0.0 and 1.0, got {priority}")
            prio = round(priority, 1)
        else:
            prio = round(self.calculate_depth_priority(path), 1)

        lm = self.format_lastmod(lastmod)

        entry = SitemapEntry(loc=loc, lastmod=lm, changefreq=cf, priority=prio)
        self.entries.append(entry)
        return entry

    def render_single_xml(self, entries: List[SitemapEntry]) -> str:
        """
        Renders a standard <urlset> XML document for the given list of entries.
        """
        urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

        for entry in entries:
            url_elem = ET.SubElement(urlset, "url")
            loc_elem = ET.SubElement(url_elem, "loc")
            loc_elem.text = entry.loc

            if entry.lastmod:
                lm_elem = ET.SubElement(url_elem, "lastmod")
                lm_elem.text = entry.lastmod

            if entry.changefreq:
                cf_elem = ET.SubElement(url_elem, "changefreq")
                cf_elem.text = entry.changefreq

            if entry.priority is not None:
                prio_elem = ET.SubElement(url_elem, "priority")
                prio_elem.text = f"{entry.priority:.1f}"

        xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")

    def render_sitemap_index(self, sitemap_locs: List[Tuple[str, Optional[str]]]) -> str:
        """
        Renders a <sitemapindex> XML document pointing to multiple partitioned sitemaps.
        Each item in sitemap_locs is a tuple of (url, optional_lastmod).
        """
        index_elem = ET.Element("sitemapindex", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

        for loc, lm in sitemap_locs:
            sitemap_elem = ET.SubElement(index_elem, "sitemap")
            loc_elem = ET.SubElement(sitemap_elem, "loc")
            loc_elem.text = loc
            if lm:
                lm_elem = ET.SubElement(sitemap_elem, "lastmod")
                lm_elem.text = lm

        xml_bytes = ET.tostring(index_elem, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")

    def generate_sitemaps(self) -> List[Tuple[str, str]]:
        """
        Generates sitemaps with automatic index partitioning.
        Returns a list of filename to XML content tuples:
        - If len(entries) <= max_urls: [("sitemap.xml", "<urlset>...")]
        - If len(entries) > max_urls: [("sitemap-1.xml", ...), ("sitemap-2.xml", ...), ("sitemap.xml", "<sitemapindex>...")]
        """
        if len(self.entries) <= self.max_urls_per_sitemap:
            return [("sitemap.xml", self.render_single_xml(self.entries))]

        # Partition entries
        results: List[Tuple[str, str]] = []
        index_entries: List[Tuple[str, Optional[str]]] = []
        total_chunks = (len(self.entries) + self.max_urls_per_sitemap - 1) // self.max_urls_per_sitemap

        today_str = date.today().strftime("%Y-%m-%d")

        for i in range(total_chunks):
            chunk = self.entries[i * self.max_urls_per_sitemap : (i + 1) * self.max_urls_per_sitemap]
            filename = f"sitemap-{i + 1}.xml"
            xml_content = self.render_single_xml(chunk)
            results.append((filename, xml_content))

            file_url = f"{self.base_url}/{filename}"
            index_entries.append((file_url, today_str))

        # Build index document as primary sitemap.xml
        index_xml = self.render_sitemap_index(index_entries)
        results.append(("sitemap.xml", index_xml))
        return results

    def render_robots_txt(
        self,
        sitemap_filename: str = "sitemap.xml",
        disallow_paths: Optional[List[str]] = None,
    ) -> str:
        """
        Generates RFC 9309 compliant robots.txt referencing the sitemap.
        """
        lines = ["User-agent: *"]
        if disallow_paths:
            for p in disallow_paths:
                clean_p = "/" + p.strip().lstrip("/")
                lines.append(f"Disallow: {clean_p}")
        else:
            lines.append("Disallow:")

        sitemap_url = f"{self.base_url}/{sitemap_filename.lstrip('/')}"
        lines.append(f"\nSitemap: {sitemap_url}\n")
        return "\n".join(lines)
