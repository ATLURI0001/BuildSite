from buildsite.asset_telemetry import (
    AssetCategory,
    AssetTelemetryCollector,
    SizeBudgetConfig,
)


def test_asset_category_from_path():
    assert AssetCategory.from_path("dist/bundle.min.js") == AssetCategory.JS
    assert AssetCategory.from_path("src/module.mjs") == AssetCategory.JS
    assert AssetCategory.from_path("styles/theme.css") == AssetCategory.CSS
    assert AssetCategory.from_path("index.html") == AssetCategory.HTML
    assert AssetCategory.from_path("assets/hero.svg") == AssetCategory.IMAGE
    assert AssetCategory.from_path("assets/photo.avif") == AssetCategory.IMAGE
    assert AssetCategory.from_path("fonts/inter.woff2") == AssetCategory.FONT
    assert AssetCategory.from_path("data/schema.json") == AssetCategory.OTHER


def test_record_asset_compression_calculation():
    collector = AssetTelemetryCollector()

    # Highly compressible repeated text
    content = "const data = " + ("'abcdef1234567890'" * 500) + ";"
    record = collector.record_asset("dist/app.js", content)

    assert record.path == "dist/app.js"
    assert record.category == AssetCategory.JS
    assert record.raw_bytes > 0
    assert record.gzip_bytes < record.raw_bytes
    assert record.compressed_ratio > 1.0
    assert record.is_budget_breach is False
    assert record.severity == "OK"


def test_record_empty_asset():
    collector = AssetTelemetryCollector()
    record = collector.record_asset("dist/empty.css", "")

    assert record.raw_bytes == 0
    assert record.gzip_bytes == 0
    assert record.compressed_ratio == 1.0
    assert record.is_budget_breach is False


def test_asset_size_budget_breach():
    # Set tiny custom budget
    budget = SizeBudgetConfig(
        max_raw_per_asset={AssetCategory.JS: 500},
        max_gzip_per_asset={AssetCategory.JS: 100},
    )
    collector = AssetTelemetryCollector(budget=budget)

    # Payload 1000 bytes > 500 max raw
    payload = "A" * 1000
    record = collector.record_asset("dist/heavy.js", payload)

    assert record.is_budget_breach is True
    assert record.severity == "CRITICAL"
    assert "breaches js ceiling" in record.breach_reason

    anomalies = collector.detect_anomalies()
    assert len(anomalies) == 1
    assert anomalies[0]["path"] == "dist/heavy.js"


def test_suboptimal_compression_warning():
    collector = AssetTelemetryCollector()
    # Incompressible random/pseudo-random content without repetitive patterns
    import os
    random_bytes = os.urandom(2048)

    # Force category to CSS
    record = collector.record_asset("dist/uncompressible.css", random_bytes, category=AssetCategory.CSS)

    # Compressed ratio will likely be around 1.0 (less than 1.15)
    assert record.is_budget_breach is True
    assert record.severity == "WARNING"
    assert "Sub-optimal compression ratio" in record.breach_reason


def test_category_summary_and_totals():
    collector = AssetTelemetryCollector()

    collector.record_asset("dist/app.js", "console.log('hello');" * 100)
    collector.record_asset("dist/styles.css", "body { color: red; }" * 100)
    collector.record_asset("dist/index.html", "<html><body>Hello</body></html>" * 50)

    summary = collector.get_category_summary()
    assert "js" in summary
    assert "css" in summary
    assert "html" in summary
    assert summary["js"]["count"] == 1
    assert summary["css"]["savings_bytes"] > 0

    assert collector.total_raw_bytes > collector.total_gzip_bytes


def test_global_bundle_budget_breach():
    budget = SizeBudgetConfig(
        max_total_raw_bytes=1000,
        max_total_gzip_bytes=500,
    )
    collector = AssetTelemetryCollector(budget=budget)

    collector.record_asset("dist/app.js", "X" * 1500)

    anomalies = collector.detect_anomalies()
    global_anomalies = [a for a in anomalies if a["path"] == "GLOBAL_BUNDLE"]
    assert len(global_anomalies) >= 1
    assert global_anomalies[0]["severity"] == "CRITICAL"


def test_diagnostic_report_and_reset():
    collector = AssetTelemetryCollector()
    collector.record_asset("dist/bundle.js", "let x = 1;" * 200)

    report = collector.generate_diagnostic_report()
    assert "# Static Asset Compression & Size Telemetry Diagnostic" in report
    assert "## Category Breakdown" in report
    assert "dist/bundle.js" not in report  # not in anomalies because it's OK

    collector.reset()
    assert collector.total_raw_bytes == 0
    assert len(collector._records) == 0
