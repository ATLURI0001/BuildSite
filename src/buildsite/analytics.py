"""Contribution calendar streak/velocity analytics and HTTP ETag conditional cache for BuildSite."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable

from buildsite.models import ContributionDay

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _compute_gini(values: list[int]) -> float:
    """Compute Gini concentration coefficient in [0.0, 1.0] for daily commit distribution."""
    n = len(values)
    if n == 0:
        return 0.0
    total = sum(values)
    if total == 0:
        return 0.0
    sorted_vals = sorted(values)
    weighted_sum = sum((i + 1) * val for i, val in enumerate(sorted_vals))
    gini = (2.0 * weighted_sum) / (n * total) - (n + 1.0) / n
    return round(max(0.0, min(1.0, gini)), 4)


def analyze_contribution_calendar(
    days: Iterable[ContributionDay | dict[str, Any]],
    *,
    reference_date: date | str | None = None,
) -> dict[str, Any]:
    """Compute exact streaks, rolling velocities, weekday profile, and Gini concentration.

    Handles unsorted/sparse calendars, duplicate dates (taking max count), leap years,
    and active-streak grace periods (today=0 still preserves streak ending yesterday).
    """
    by_date: dict[date, int] = {}
    for entry in days or ():
        raw_date = entry.date if isinstance(entry, ContributionDay) else (entry.get("date") if isinstance(entry, dict) else None)
        raw_count = entry.count if isinstance(entry, ContributionDay) else (entry.get("count", 0) if isinstance(entry, dict) else 0)
        if not isinstance(raw_date, str):
            continue
        try:
            d = date.fromisoformat(raw_date.strip()[:10])
            c = max(0, int(raw_count))
        except (ValueError, TypeError):
            continue
        by_date[d] = max(by_date.get(d, 0), c)

    if not by_date:
        return {
            "total_contributions": 0,
            "active_days": 0,
            "longest_streak": 0,
            "longest_streak_range": None,
            "current_streak": 0,
            "velocity_7d": 0.0,
            "velocity_30d": 0.0,
            "weekday_totals": {w: 0 for w in _WEEKDAYS},
            "gini_concentration": 0.0,
        }

    all_dates = sorted(by_date.keys())
    if isinstance(reference_date, str):
        ref = date.fromisoformat(reference_date.strip()[:10])
    elif isinstance(reference_date, date):
        ref = reference_date
    else:
        ref = all_dates[-1]

    # Longest streak via exact calendar-day adjacency
    longest = 0
    longest_range: tuple[str, str] | None = None
    run = 0
    run_start: date | None = None
    prev_active: date | None = None

    weekday_totals = {w: 0 for w in _WEEKDAYS}
    total_contribs = 0
    active_days = 0

    for d in all_dates:
        c = by_date[d]
        total_contribs += c
        weekday_totals[_WEEKDAYS[d.weekday()]] += c
        if c > 0:
            active_days += 1
            if prev_active is not None and (d - prev_active) == timedelta(days=1):
                run += 1
            else:
                run = 1
                run_start = d
            prev_active = d
            if run > longest:
                longest = run
                longest_range = (run_start.isoformat(), d.isoformat())  # type: ignore[union-attr]

    # Current streak anchored at reference_date (with 1-day grace if today is not yet committed)
    current_streak = 0
    cursor = ref if by_date.get(ref, 0) > 0 else ref - timedelta(days=1)
    while by_date.get(cursor, 0) > 0:
        current_streak += 1
        cursor -= timedelta(days=1)

    # 7-day and 30-day rolling daily velocity ending at reference_date
    sum_7d = sum(by_date.get(ref - timedelta(days=offset), 0) for offset in range(7))
    sum_30d = sum(by_date.get(ref - timedelta(days=offset), 0) for offset in range(30))

    return {
        "total_contributions": total_contribs,
        "active_days": active_days,
        "longest_streak": longest,
        "longest_streak_range": longest_range,
        "current_streak": current_streak,
        "velocity_7d": round(sum_7d / 7.0, 2),
        "velocity_30d": round(sum_30d / 30.0, 2),
        "weekday_totals": weekday_totals,
        "gini_concentration": _compute_gini(list(by_date.values())),
    }


@dataclass
class _ETagEntry:
    etag: str
    payload: Any
    stored_at: float
    ttl_seconds: float


class ConditionalETagCache:
    """Bounded LRU HTTP conditional-request cache supporting GitHub ETag / 304 Not Modified flows."""

    def __init__(
        self,
        *,
        max_entries: int = 256,
        default_ttl_seconds: float = 300.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self.max_entries = int(max_entries)
        self.default_ttl_seconds = float(default_ttl_seconds)
        self._clock = clock if callable(clock) else time.monotonic
        self._store: OrderedDict[str, _ETagEntry] = OrderedDict()
        self.hits_fresh = 0
        self.hits_304 = 0
        self.misses = 0

    def _normalize_key(self, key: Any) -> str:
        if not isinstance(key, str):
            key = str(key)
        cleaned = key.strip()
        if not cleaned:
            raise ValueError("cache key cannot be empty")
        return cleaned

    def get_conditional_headers(self, key: str) -> dict[str, str]:
        """Return If-None-Match header when an ETag exists for key, even if TTL elapsed."""
        k = self._normalize_key(key)
        entry = self._store.get(k)
        if entry is None or not entry.etag:
            return {}
        return {"If-None-Match": entry.etag}

    def get_fresh(self, key: str) -> Any | None:
        """Return cached payload if present and within TTL, otherwise None."""
        k = self._normalize_key(key)
        entry = self._store.get(k)
        if entry is None:
            self.misses += 1
            return None
        if (self._clock() - entry.stored_at) > entry.ttl_seconds:
            self.misses += 1
            return None
        self._store.move_to_end(k)
        self.hits_fresh += 1
        return entry.payload

    def store(self, key: str, payload: Any, etag: str = "", ttl_seconds: float | None = None) -> None:
        """Store or refresh a response payload and optional ETag with LRU bounding."""
        k = self._normalize_key(key)
        ttl = self.default_ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        if k in self._store:
            self._store.move_to_end(k)
        elif len(self._store) >= self.max_entries:
            self._store.popitem(last=False)
        self._store[k] = _ETagEntry(
            etag=etag.strip(),
            payload=payload,
            stored_at=self._clock(),
            ttl_seconds=max(0.0, ttl),
        )

    def handle_not_modified(self, key: str, ttl_seconds: float | None = None) -> Any | None:
        """Refresh TTL and return cached payload upon HTTP 304 Not Modified from GitHub API."""
        k = self._normalize_key(key)
        entry = self._store.get(k)
        if entry is None:
            self.misses += 1
            return None
        entry.stored_at = self._clock()
        if ttl_seconds is not None:
            entry.ttl_seconds = max(0.0, float(ttl_seconds))
        self._store.move_to_end(k)
        self.hits_304 += 1
        return entry.payload

    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._store),
            "hits_fresh": self.hits_fresh,
            "hits_304": self.hits_304,
            "misses": self.misses,
        }
