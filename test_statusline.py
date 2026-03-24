"""Tests for statusline.py."""

import json
import time

import statusline as sl


# ── _severity_rgb ────────────────────────────────────────────────

def test_severity_rgb_green_at_zero():
    r, g, b = sl._severity_rgb(0.0)
    assert g > r and g > b, f"Expected green-dominant, got ({r},{g},{b})"


def test_severity_rgb_red_at_one():
    r, g, b = sl._severity_rgb(1.0)
    assert r > g and r > b, f"Expected red-dominant, got ({r},{g},{b})"


def test_severity_rgb_yellow_at_half():
    r, g, b = sl._severity_rgb(0.5)
    assert r > 150 and g > 150 and b < 100, f"Expected yellowish, got ({r},{g},{b})"


def test_severity_rgb_clamps():
    assert sl._severity_rgb(-0.5) == sl._severity_rgb(0.0)
    assert sl._severity_rgb(1.5) == sl._severity_rgb(1.0)


def test_severity_rgb_monotonic_hue():
    """Green component should decrease as severity rises."""
    prev_g = 999
    for i in range(0, 101, 10):
        _, g, _ = sl._severity_rgb(i / 100)
        assert g <= prev_g or i == 0, f"Green not monotonically decreasing at {i}%"
        prev_g = g


# ── tint / gauge at 0% ──────────────────────────────────────────

def test_tint_zero_is_faint():
    result = sl.tint(0, "hello")
    assert "\x1b[2m" in result, "0% should use faint styling"
    assert "38;2;" not in result, "0% should not use truecolor"


def test_tint_positive_is_truecolor():
    result = sl.tint(50, "hello")
    assert "38;2;" in result, "50% should use truecolor"


def test_gauge_zero_is_blank():
    result = sl.gauge(0, 10)
    assert "48;2;50;50;50" in result, "0% gauge should be blank background"
    assert "█" not in result


def test_gauge_100_all_filled():
    result = sl.gauge(100, 6)
    assert "██████" in result
    assert "48;2;50;50;50" not in result, "100% gauge should have no empty bg"


def test_gauge_clamps():
    sl.gauge(-10, 6)  # should not raise
    sl.gauge(200, 6)  # should not raise


# ── Formatters ───────────────────────────────────────────────────

def test_compact_duration_seconds():
    assert sl.compact_duration(5000) == "5s"


def test_compact_duration_minutes():
    assert sl.compact_duration(125000) == "2m05s"


def test_compact_duration_hours():
    assert sl.compact_duration(7200000) == "2h00m"


def test_countdown_past():
    assert sl.countdown(time.time() - 10) == "now"


def test_countdown_seconds():
    result = sl.countdown(time.time() + 30)
    assert result.endswith("s")


def test_countdown_minutes():
    result = sl.countdown(time.time() + 300)
    assert result.endswith("m")


def test_abbrev_path_home():
    import os
    home = os.path.expanduser("~")
    assert sl.abbrev_path(f"{home}/projects") == "~/projects"


def test_abbrev_path_other():
    assert sl.abbrev_path("/var/log") == "/var/log"


# ── rate_segment ─────────────────────────────────────────────────

def test_rate_segment_none():
    result = sl.rate_segment("5h", None, None)
    assert "--%"  in result


def test_rate_segment_with_data():
    result = sl.rate_segment("5h", 42, time.time() + 3600)
    assert "42%" in result
    assert "5h" in result


# ── render (integration) ────────────────────────────────────────

def _render(overrides: dict = {}) -> str:
    base = {
        "model": {"display_name": "Test"},
        "workspace": {"current_dir": "/tmp"},
        "context_window": {"used_percentage": 25},
        "cost": {"total_cost_usd": 1.0, "total_duration_ms": 60000},
        "rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": time.time() + 3600},
            "seven_day": {"used_percentage": 5, "resets_at": time.time() + 86400},
        },
    }
    base.update(overrides)
    return sl.render(base)


def test_render_two_lines():
    out = _render()
    assert out.count("\n") == 1, "Should produce exactly two lines"


def test_render_contains_model():
    out = _render()
    assert "Test" in out


def test_render_contains_cost():
    out = _render()
    assert "$1.00" in out


def test_render_empty_data():
    out = sl.render({})
    assert out is not None


def test_render_no_rate_limits():
    out = _render({"rate_limits": {}})
    assert "--%"  in out
