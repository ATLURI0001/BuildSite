"""Unit tests for contribution calendar streak/velocity analytics and HTTP ETag cache."""

from datetime import date

from buildsite.analytics import ConditionalETagCache, analyze_contribution_calendar
from buildsite.models import ContributionDay


def test_analyze_contribution_calendar_leap_year_streaks_and_velocity():
    # Spans leap day 2024-02-29 cleanly
    days = [
        ContributionDay(date="2024-02-28", count=5),
        ContributionDay(date="2024-02-29", count=7),
        ContributionDay(date="2024-03-01", count=4),
        ContributionDay(date="2024-03-02", count=0),  # gap breaks streak
        ContributionDay(date="2024-03-03", count=6),
        ContributionDay(date="2024-03-04", count=8),
    ]
    report = analyze_contribution_calendar(days, reference_date=date(2024, 3, 5))
    assert report["total_contributions"] == 30
    assert report["active_days"] == 5
    assert report["longest_streak"] == 3
    assert report["longest_streak_range"] == ("2024-02-28", "2024-03-01")
    # Grace day: reference_date is Mar 5 (0 commits), Mar 4 and Mar 3 active -> current streak = 2
    assert report["current_streak"] == 2
    assert report["velocity_7d"] == round(30 / 7.0, 2)
    assert report["velocity_30d"] == round(30 / 30.0, 2)
    assert 0.0 <= report["gini_concentration"] <= 1.0

    # Empty fallback
    empty = analyze_contribution_calendar([])
    assert empty["longest_streak"] == 0
    assert empty["longest_streak_range"] is None


def test_conditional_etag_cache_ttl_304_revalidation_and_lru():
    now = [100.0]
    cache = ConditionalETagCache(max_entries=2, default_ttl_seconds=60.0, clock=lambda: now[0])

    cache.store("user:alice", {"commits": 120}, etag='W/"abc123"')
    assert cache.get_fresh("user:alice") == {"commits": 120}
    assert cache.get_conditional_headers("user:alice") == {"If-None-Match": 'W/"abc123"'}

    # Advance past TTL -> fresh cache misses, but ETag header remains available for 304 revalidation
    now[0] = 200.0
    assert cache.get_fresh("user:alice") is None
    assert cache.get_conditional_headers("user:alice") == {"If-None-Match": 'W/"abc123"'}

    # Server returns 304 Not Modified -> refreshes TTL without spending API quota
    revalidated = cache.handle_not_modified("user:alice")
    assert revalidated == {"commits": 120}
    assert cache.get_fresh("user:alice") == {"commits": 120}

    # LRU bounding (max_entries=2): add bob, then carol -> evicts alice (or oldest untouched)
    cache.store("user:bob", {"commits": 50}, etag='W/"bob"')
    # Touch alice so bob becomes LRU
    assert cache.get_fresh("user:alice") == {"commits": 120}
    cache.store("user:carol", {"commits": 10}, etag='W/"carol"')

    assert cache.get_fresh("user:bob") is None
    assert cache.get_fresh("user:carol") == {"commits": 10}
    stats = cache.stats()
    assert stats["entries"] == 2
    assert stats["hits_304"] == 1


def test_conditional_etag_cache_miss_on_unmapped_304_and_key_normalization():
    cache = ConditionalETagCache(max_entries=4)
    cache.store("  user:octocat  ", {"data": 123}, etag='W/"xyz"')
    assert cache.get_fresh("user:octocat") == {"data": 123}

    assert cache.handle_not_modified("user:unknown") is None
    assert cache.stats()["misses"] == 1

    import pytest
    with pytest.raises(ValueError, match="cache key cannot be empty"):
        cache.get_fresh("   ")


def test_conditional_etag_cache_invalidation_clear_and_dunder_methods():
    now = [10.0]
    cache = ConditionalETagCache(max_entries=5, default_ttl_seconds=50.0, clock=lambda: now[0])

    assert len(cache) == 0
    assert "user:alpha" not in cache

    cache.store("user:alpha", {"val": 1}, etag="etag1")
    cache.store("user:beta", {"val": 2}, etag="etag2")

    assert len(cache) == 2
    assert "user:alpha" in cache
    assert "  user:beta  " in cache
    assert "user:gamma" not in cache

    # Expired check via __contains__
    now[0] = 70.0
    assert "user:alpha" not in cache

    # Invalidate specific entry
    now[0] = 10.0
    cache.store("user:alpha", {"val": 1}, etag="etag1")
    assert cache.invalidate("user:alpha") is True
    assert cache.invalidate("user:alpha") is False
    assert cache.invalidate("   ") is False
    assert len(cache) == 1

    # Clear entire cache
    cache.clear()
    assert len(cache) == 0
    assert "user:beta" not in cache


def test_analyze_contribution_calendar_none_count_handling():
    days = [
        {"date": "2024-04-01", "count": None},
        {"date": "2024-04-02", "count": 3},
    ]
    report = analyze_contribution_calendar(days, reference_date=date(2024, 4, 3))
    assert report["total_contributions"] == 3
    assert report["active_days"] == 1
    assert report["current_streak"] == 1

