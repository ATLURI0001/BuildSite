"""
BuildSite Markdown Parsing & HTML Compilation Latency Benchmark Profiler.

Profiles tokenization throughput, regex match overhead, AST translation,
and HTML generation performance across varying content document tiers.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CompilerBenchmarkReport:
    document_size_tier: str
    iterations: int
    total_duration_ms: float
    throughput_docs_per_sec: float
    throughput_mb_per_sec: float
    mean_latency_ms: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    total_bytes_processed: int


class MarkdownCompilerProfiler:
    """
    Lightweight, deterministic Markdown-to-HTML parser and benchmark profiler.
    """

    RE_HEADER = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    RE_CODE_BLOCK = re.compile(r"```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```", re.MULTILINE)
    RE_INLINE_CODE = re.compile(r"`([^`]+)`")
    RE_BOLD = re.compile(r"\*\*([^*]+)\*\*")
    RE_ITALIC = re.compile(r"\*([^*]+)\*")
    RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    RE_UNORDERED_LIST = re.compile(r"^\s*[-*+]\s+(.+)$", re.MULTILINE)

    def compile_to_html(self, markdown_text: str) -> str:
        """
        Parses Markdown text and compiles to sanitized HTML output.
        """
        if not isinstance(markdown_text, str):
            raise TypeError("markdown_text must be a string")

        if not markdown_text.strip():
            return ""

        # 1. Protect code blocks by placeholder
        code_blocks: List[str] = []

        def replace_code_block(match: re.Match) -> str:
            lang = html.escape(match.group(1))
            code = html.escape(match.group(2))
            idx = len(code_blocks)
            code_blocks.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
            return f"<!--CODE_BLOCK_{idx}-->"

        content = self.RE_CODE_BLOCK.sub(replace_code_block, markdown_text)

        # 2. Inline transformations
        content = self.RE_HEADER.sub(
            lambda m: f"<h{len(m.group(1))}>{html.escape(m.group(2))}</h{len(m.group(1))}>",
            content,
        )
        content = self.RE_INLINE_CODE.sub(
            lambda m: f"<code>{html.escape(m.group(1))}</code>",
            content,
        )
        content = self.RE_BOLD.sub(
            lambda m: f"<strong>{html.escape(m.group(1))}</strong>",
            content,
        )
        content = self.RE_ITALIC.sub(
            lambda m: f"<em>{html.escape(m.group(1))}</em>",
            content,
        )
        content = self.RE_LINK.sub(
            lambda m: f'<a href="{html.escape(m.group(2))}">{html.escape(m.group(1))}</a>',
            content,
        )
        content = self.RE_UNORDERED_LIST.sub(
            lambda m: f"<li>{html.escape(m.group(1))}</li>",
            content,
        )

        # 3. Restore code blocks
        for i, block in enumerate(code_blocks):
            content = content.replace(f"<!--CODE_BLOCK_{i}-->", block)

        return content

    def create_synthetic_markdown(self, target_size_bytes: int = 1024) -> str:
        """
        Generates realistic synthetic Markdown document approximating a given byte size.
        """
        sections: List[str] = [
            "# Architecture Overview",
            "This document describes the high-throughput compilation engine for static sites.",
            "## Component Specifications",
            "- **Lexer**: Tokenizes raw character streams with regex lookaheads.",
            "- **Parser**: Constructs deterministic AST nodes with link validation.",
            "- **Emitter**: Emits clean, sanitized HTML compliant with CSP standards.",
            "```python\ndef compile_site(source_dir: str) -> None:\n    print(f'Building site from {source_dir}')\n```",
            "See the official [Documentation](https://docs.example.com) for configuration details.",
        ]
        base_text = "\n\n".join(sections)
        repeat_count = max(1, target_size_bytes // len(base_text.encode("utf-8")))

        full_doc = "\n\n".join(
            [f"# Section {i}\n" + base_text for i in range(repeat_count)]
        )
        return full_doc

    def profile_compiler(
        self, iterations: int = 500, size_tier: str = "standard"
    ) -> CompilerBenchmarkReport:
        """
        Runs an isolated benchmarking loop measuring parsing throughput and latency distributions.
        """
        if iterations <= 0:
            raise ValueError("iterations must be a positive integer")

        target_size = 1024 if size_tier == "compact" else 32768 if size_tier == "jumbo" else 8192
        doc = self.create_synthetic_markdown(target_size)
        doc_bytes = len(doc.encode("utf-8"))

        latencies_ms: List[float] = [0.0] * iterations
        total_bytes = 0

        start_time = time.perf_counter()

        for i in range(iterations):
            iter_start = time.perf_counter()
            _ = self.compile_to_html(doc)
            iter_end = time.perf_counter()

            dur_ms = (iter_end - iter_start) * 1000.0
            if dur_ms <= 0:
                dur_ms = 0.01
            latencies_ms[i] = dur_ms
            total_bytes += doc_bytes

        end_time = time.perf_counter()
        total_dur_ms = max(0.1, (end_time - start_time) * 1000.0)

        latencies_ms.sort()
        mean_lat = sum(latencies_ms) / iterations
        p50 = latencies_ms[int(iterations * 0.50)]
        p90 = latencies_ms[min(iterations - 1, int(iterations * 0.90))]
        p99 = latencies_ms[min(iterations - 1, int(iterations * 0.99))]

        throughput_docs = (iterations / total_dur_ms) * 1000.0
        throughput_mb = (total_bytes / (1024 * 1024)) / (total_dur_ms / 1000.0)

        return CompilerBenchmarkReport(
            document_size_tier=size_tier,
            iterations=iterations,
            total_duration_ms=round(total_dur_ms, 2),
            throughput_docs_per_sec=round(throughput_docs, 2),
            throughput_mb_per_sec=round(throughput_mb, 2),
            mean_latency_ms=round(mean_lat, 3),
            p50_latency_ms=round(p50, 3),
            p90_latency_ms=round(p90, 3),
            p99_latency_ms=round(p99, 3),
            total_bytes_processed=total_bytes,
        )
