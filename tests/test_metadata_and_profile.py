"""Unit tests for SiteMetadata, CohortRecord, and ProfileConfig."""
import os
from buildsite.metadata import SiteMetadata
from buildsite.cohorts import CohortRecord, aggregate_cohort_retention
from buildsite.profile import ProfileConfig


def test_site_metadata():
    meta = SiteMetadata(title="My Site", slug="my-site", tags=["python", "3d"], is_published=True)
    assert meta.validate() is True
    assert meta.to_dict()["title"] == "My Site"

    invalid_meta = SiteMetadata(title="   ", slug="", tags=[])
    assert invalid_meta.validate() is False


def test_cohort_record():
    cohort = CohortRecord(cohort_id="2026-Q1", total_users=100, active_users=85)
    assert cohort.retention_rate == 0.85

    empty_cohort = CohortRecord(cohort_id="2026-Q2", total_users=0, active_users=0)
    assert empty_cohort.retention_rate == 0.0

    records = [cohort, empty_cohort]
    agg = aggregate_cohort_retention(records)
    assert agg["2026-Q1"] == 0.85
    assert agg["2026-Q2"] == 0.0


def test_profile_config(monkeypatch):
    monkeypatch.setenv("BUILDSITE_ENV", "staging")
    monkeypatch.setenv("BUILDSITE_DEBUG", "true")
    monkeypatch.setenv("BUILDSITE_API_ENDPOINT", "https://staging.buildsite.local")

    cfg = ProfileConfig.load_from_env()
    assert cfg.env_name == "staging"
    assert cfg.debug is True
    assert cfg.api_endpoint == "https://staging.buildsite.local"
