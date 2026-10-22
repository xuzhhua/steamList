from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.analytics import (
    Point,
    build_series,
    compute_stats,
    range_start,
)

NOW = datetime(2026, 10, 22, 12, 0, 0)


def pt(days_ago: float, final: int, *, initial: int | None = None, discount: int = 0,
       available: bool = True) -> Point:
    return Point(
        at=NOW - timedelta(days=days_ago),
        initial_cents=initial if initial is not None else final,
        final_cents=final,
        discount_percent=discount,
        available=available,
    )


def sample_points() -> list[Point]:
    return [
        pt(10, 29800),
        pt(5, 14900, initial=29800, discount=50),
        pt(2, 29800),
        pt(1, 14900, initial=29800, discount=50),
    ]


def test_empty_series_and_stats():
    assert build_series([], None, NOW) == []
    stats = compute_stats([], NOW)
    assert stats["atl_cents"] is None
    assert stats["change_count"] == 0
    assert stats["days_tracked"] == 0
    assert stats["discounting"] is False


def test_build_series_prepends_anchor():
    points = sample_points()
    series = build_series(points, NOW - timedelta(days=6), NOW)
    assert len(series) == 4
    assert series[0]["final"] == 29800
    assert series[0]["t"].endswith("Z")
    assert [p["final"] for p in series] == [29800, 14900, 29800, 14900]
    assert series[1]["discount"] == 50


def test_build_series_without_window_keeps_all_points():
    series = build_series(sample_points(), None, NOW)
    assert len(series) == 4


def test_stats_on_sample_points():
    stats = compute_stats(sample_points(), NOW)
    assert stats["atl_cents"] == 14900
    assert stats["atl_hit_count"] == 3
    assert stats["atl_first_at"] == (NOW - timedelta(days=5)).isoformat() + "Z"
    assert stats["atl_last_at"] == (NOW - timedelta(days=1)).isoformat() + "Z"
    assert stats["discount_event_count"] == 2
    assert stats["discount_days"] == 4.0
    assert stats["max_discount_percent"] == 50
    assert stats["avg_discount_percent"] == 50.0
    assert stats["avg_interval_days"] == 4.0
    assert stats["days_tracked"] == 10
    assert stats["current_final_cents"] == 14900
    assert stats["discounting"] is True
    assert stats["last_discount_at"] is not None


def test_stats_open_episode_ends_now():
    points = [pt(40, 29800), pt(1, 14900, discount=50)]
    stats = compute_stats(points, NOW)
    assert stats["discount_event_count"] == 1
    assert stats["discount_days"] == 1.0
    assert stats["avg_interval_days"] is None


def test_unavailable_points_do_not_become_atl():
    points = [pt(3, 29800), pt(2, 0, available=False), pt(1, 29800)]
    stats = compute_stats(points, NOW)
    assert stats["atl_cents"] == 29800
    assert stats["atl_hit_count"] == 1


def test_range_start_values():
    assert range_start("all", NOW) is None
    assert range_start("30d", NOW) == NOW - timedelta(days=30)
    with pytest.raises(ValueError):
        range_start("7d", NOW)
