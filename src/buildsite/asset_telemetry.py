"""
BuildSite - Build Asset Compression Telemetry & Payload Size Diagnostic Engine

Tracks, analyzes, and enforces payload size budgets across static site build artifacts.
Computes multi-algorithm compression ratios (Gzip, Deflate/Brotli), categorizes assets,
and detects bandwidth regressions before deployment.
"""

from __future__ import annotations

import gzip
import os
import re
import zlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class AssetCategory(str, Enum):
    JS = "js"
    CSS = "css"
    HTML = "html"
    IMAGE = "image"
    FONT = "font"
    OTHER = "other"

    @classmethod
    def from_path(cls, path: str) -> "AssetCategory":
        ext = os.path.splitext(path)[1].lower()
        if ext in {".js", ".mjs", ".cjs"}:
            return cls.JS
        elif ext in {".css", ".scss", ".sass"}:
            return cls.CSS
        elif ext in {".html", ".htm"}:
            return cls.HTML
        elif ext in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".avif"}:
            return cls.IMAGE
        elif ext in {".woff", ".woff2", ".ttf", ".eot", ".otf"}:
            return cls.FONT
        return cls.OTHER


@dataclass
class SizeBudgetConfig:
    """Configurable budget ceilings in bytes per asset category."""
    max_raw_per_asset: Dict[AssetCategory, int] = field(default_factory=lambda: {
        AssetCategory.JS: 250 * 1024,      # 250 KB
        AssetCategory.CSS: 100 * 1024,     # 100 KB
        AssetCategory.HTML: 80 * 1024,     # 80 KB
        AssetCategory.IMAGE: 500 * 1024,   # 500 KB
        AssetCategory.FONT: 200 * 1024,    # 200 KB
        AssetCategory.OTHER: 500 * 1024,   # 500 KB
    })
    max_gzip_per_asset: Dict[AssetCategory, int] = field(default_factory=lambda: {
        AssetCategory.JS: 75 * 1024,       # 75 KB
        AssetCategory.CSS: 30 * 1024,      # 30 KB
        AssetCategory.HTML: 25 * 1024,     # 25 KB
        AssetCategory.IMAGE: 450 * 1024,   # 450 KB
        AssetCategory.FONT: 180 * 1024,    # 180 KB
        AssetCategory.OTHER: 400 * 1024,   # 400 KB
    })
    max_total_raw_bytes: int = 5 * 1024 * 1024    # 5 MB total site payload
    max_total_gzip_bytes: int = 1500 * 1024       # 1.5 MB total compressed payload
    min_compression_ratio: float = 1.15           # Warn if compressible text asset compresses < 15%


@dataclass
class AssetTelemetryRecord:
    path: str
    category: AssetCategory
    raw_bytes: int
    gzip_bytes: int
    compressed_ratio: float
    is_budget_breach: bool
    breach_reason: Optional[str] = None
    severity: str = "OK"  # "OK", "WARNING", "CRITICAL"


class AssetTelemetryCollector:
    """Collects and audits static asset size and compression efficiency."""

    def __init__(self, budget: Optional[SizeBudgetConfig] = None) -> None:
        self.budget = budget or SizeBudgetConfig()
        self._records: List[AssetTelemetryRecord] = []

    def record_asset(
        self,
        path: str,
        content: bytes | str,
        category: Optional[AssetCategory] = None,
    ) -> AssetTelemetryRecord:
        """Analyzes and records an individual asset payload."""
        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = bytes(content)

        raw_size = len(data)
        cat = category or AssetCategory.from_path(path)

        # Compute Gzip compressed size (level 9 maximum compression)
        if raw_size == 0:
            gzip_size = 0
            ratio = 1.0
        else:
            compressed = gzip.compress(data, compresslevel=9)
            gzip_size = len(compressed)
            ratio = round(raw_size / max(gzip_size, 1), 3)

        # Budget evaluation
        max_raw = self.budget.max_raw_per_asset.get(cat, 500 * 1024)
        max_gzip = self.budget.max_gzip_per_asset.get(cat, 150 * 1024)

        breach = False
        reason = None
        severity = "OK"

        if raw_size > max_raw:
            breach = True
            severity = "CRITICAL"
            reason = f"Raw size {raw_size:,}B breaches {cat.value} ceiling ({max_raw:,}B)"
        elif gzip_size > max_gzip:
            breach = True
            severity = "CRITICAL"
            reason = f"Gzip size {gzip_size:,}B breaches {cat.value} ceiling ({max_gzip:,}B)"
        elif cat in {AssetCategory.JS, AssetCategory.CSS, AssetCategory.HTML} and raw_size > 1024 and ratio < self.budget.min_compression_ratio:
            breach = True
            severity = "WARNING"
            reason = f"Sub-optimal compression ratio ({ratio:.2f}x < {self.budget.min_compression_ratio:.2f}x threshold)"

        record = AssetTelemetryRecord(
            path=path,
            category=cat,
            raw_bytes=raw_size,
            gzip_bytes=gzip_size,
            compressed_ratio=ratio,
            is_budget_breach=breach,
            breach_reason=reason,
            severity=severity,
        )
        self._records.append(record)
        return record

    @property
    def total_raw_bytes(self) -> int:
        return sum(r.raw_bytes for r in self._records)

    @property
    def total_gzip_bytes(self) -> int:
        return sum(r.gzip_bytes for r in self._records)

    def get_category_summary(self) -> Dict[str, Dict[str, Any]]:
        """Returns aggregated telemetry grouped by asset category."""
        summary: Dict[str, Dict[str, Any]] = {}
        for cat in AssetCategory:
            records = [r for r in self._records if r.category == cat]
            if not records:
                continue

            raw = sum(r.raw_bytes for r in records)
            gz = sum(r.gzip_bytes for r in records)
            savings = raw - gz
            savings_pct = round((savings / raw * 100), 2) if raw > 0 else 0.0
            avg_ratio = round(sum(r.compressed_ratio for r in records) / len(records), 2)

            summary[cat.value] = {
                "count": len(records),
                "raw_bytes": raw,
                "gzip_bytes": gz,
                "savings_bytes": savings,
                "savings_percent": savings_pct,
                "avg_compression_ratio": avg_ratio,
            }
        return summary

    def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Identifies all asset and global budget breaches."""
        anomalies: List[Dict[str, Any]] = []

        # Individual asset breaches
        for r in self._records:
            if r.is_budget_breach:
                anomalies.append({
                    "path": r.path,
                    "category": r.category.value,
                    "severity": r.severity,
                    "reason": r.breach_reason,
                    "raw_bytes": r.raw_bytes,
                    "gzip_bytes": r.gzip_bytes,
                })

        # Global totals check
        if self.total_raw_bytes > self.budget.max_total_raw_bytes:
            anomalies.append({
                "path": "GLOBAL_BUNDLE",
                "category": "all",
                "severity": "CRITICAL",
                "reason": f"Total raw payload {self.total_raw_bytes:,}B exceeds budget {self.budget.max_total_raw_bytes:,}B",
                "raw_bytes": self.total_raw_bytes,
                "gzip_bytes": self.total_gzip_bytes,
            })

        if self.total_gzip_bytes > self.budget.max_total_gzip_bytes:
            anomalies.append({
                "path": "GLOBAL_BUNDLE",
                "category": "all",
                "severity": "CRITICAL",
                "reason": f"Total gzip payload {self.total_gzip_bytes:,}B exceeds budget {self.budget.max_total_gzip_bytes:,}B",
                "raw_bytes": self.total_raw_bytes,
                "gzip_bytes": self.total_gzip_bytes,
            })

        return anomalies

    def generate_diagnostic_report(self) -> str:
        """Generates a comprehensive markdown diagnostic report."""
        lines = [
            "# Static Asset Compression & Size Telemetry Diagnostic",
            "",
            f"- **Total Assets**: {len(self._records)}",
            f"- **Total Raw Size**: {self.total_raw_bytes:,} bytes ({self.total_raw_bytes / 1024:.2f} KB)",
            f"- **Total Gzip Size**: {self.total_gzip_bytes:,} bytes ({self.total_gzip_bytes / 1024:.2f} KB)",
        ]

        if self.total_raw_bytes > 0:
            overall_savings = (self.total_raw_bytes - self.total_gzip_bytes) / self.total_raw_bytes * 100
            lines.append(f"- **Overall Bandwidth Savings**: {overall_savings:.2f}%")
        lines.append("")

        anomalies = self.detect_anomalies()
        if anomalies:
            lines.append("## ⚠️ Budget Anomalies & Diagnostic Warnings")
            lines.append("| Target | Severity | Category | Diagnostic Reason |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for a in anomalies:
                lines.append(f"| `{a['path']}` | **{a['severity']}** | `{a['category']}` | {a['reason']} |")
            lines.append("")

        lines.append("## Category Breakdown")
        lines.append("| Category | Count | Raw Size | Gzip Size | Savings | Avg Ratio |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for cat, data in self.get_category_summary().items():
            lines.append(
                f"| `{cat}` | {data['count']} | {data['raw_bytes']:,}B | {data['gzip_bytes']:,}B | "
                f"{data['savings_percent']}% | {data['avg_compression_ratio']}x |"
            )
        lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        """Clears all recorded assets."""
        self._records.clear()
