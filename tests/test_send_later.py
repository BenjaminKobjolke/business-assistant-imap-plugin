"""Tests for send_later module — business-hours scheduling + RFC 5322 formatting."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from business_assistant_imap.send_later import (
    build_send_later_headers,
    calculate_next_send_time,
    format_rfc5322,
)

TZ = ZoneInfo("Europe/Berlin")


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


class TestCalculateNextSendTime:
    """Tests for calculate_next_send_time."""

    def test_weekday_within_hours_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 10, 30)  # Monday 10:30
        assert calculate_next_send_time(now) is None

    def test_weekday_at_start_hour_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 8, 0)  # Monday 08:00
        assert calculate_next_send_time(now) is None

    def test_weekday_before_start_returns_none(self) -> None:
        """Before business hours on a weekday — user will be at desk soon."""
        now = _dt(2026, 3, 16, 6, 30)  # Monday 06:30
        assert calculate_next_send_time(now) is None

    def test_weekday_just_before_start_returns_none(self) -> None:
        """5 minutes before start — no header needed."""
        now = _dt(2026, 3, 16, 7, 55)  # Monday 07:55
        assert calculate_next_send_time(now) is None

    def test_weekday_at_end_hour_returns_next_day(self) -> None:
        now = _dt(2026, 3, 16, 18, 0)  # Monday 18:00
        expected = _dt(2026, 3, 17, 8, 0)  # Tuesday 08:00
        assert calculate_next_send_time(now) == expected

    def test_weekday_after_end_hour_returns_next_day(self) -> None:
        now = _dt(2026, 3, 17, 20, 0)  # Tuesday 20:00
        expected = _dt(2026, 3, 18, 8, 0)  # Wednesday 08:00
        assert calculate_next_send_time(now) == expected

    def test_friday_after_hours_returns_monday(self) -> None:
        now = _dt(2026, 3, 20, 19, 0)  # Friday 19:00
        expected = _dt(2026, 3, 23, 8, 0)  # Monday 08:00
        assert calculate_next_send_time(now) == expected

    def test_saturday_returns_monday(self) -> None:
        now = _dt(2026, 3, 21, 12, 0)  # Saturday
        expected = _dt(2026, 3, 23, 8, 0)  # Monday 08:00
        assert calculate_next_send_time(now) == expected

    def test_sunday_returns_monday(self) -> None:
        now = _dt(2026, 3, 15, 14, 0)  # Sunday
        expected = _dt(2026, 3, 16, 8, 0)  # Monday 08:00
        assert calculate_next_send_time(now) == expected

    def test_custom_hours_before_start_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 9, 30)  # Monday 09:30
        # With start_hour=10, 09:30 is before start → None (weekday daytime).
        assert calculate_next_send_time(now, start_hour=10, end_hour=16) is None

    def test_custom_hours_within_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 12, 0)  # Monday 12:00
        assert calculate_next_send_time(now, start_hour=10, end_hour=16) is None

    def test_custom_hours_after_end_schedules(self) -> None:
        now = _dt(2026, 3, 16, 16, 30)  # Monday 16:30, end=16
        expected = _dt(2026, 3, 17, 10, 0)  # Tuesday 10:00
        assert calculate_next_send_time(now, start_hour=10, end_hour=16) == expected


class TestFormatRFC5322:
    """Tests for format_rfc5322."""

    def test_basic_format(self) -> None:
        dt = _dt(2026, 3, 16, 8, 0)  # Monday
        result = format_rfc5322(dt)
        assert result.startswith("Mon, 16 Mar 2026 08:00:00")

    def test_includes_timezone_offset(self) -> None:
        dt = _dt(2026, 3, 16, 8, 0)
        result = format_rfc5322(dt)
        # Europe/Berlin in March is CET = +0100
        assert result.endswith("+0100")

    def test_summer_time_offset(self) -> None:
        # After DST switch (last Sunday of March), Europe/Berlin = +0200
        dt = _dt(2026, 7, 1, 10, 0)  # July — CEST
        result = format_rfc5322(dt)
        assert result.endswith("+0200")

    def test_day_names(self) -> None:
        # 2026-03-16 is Monday, 2026-03-17 is Tuesday, etc.
        for day, name in [(16, "Mon"), (17, "Tue"), (18, "Wed"),
                          (19, "Thu"), (20, "Fri"), (21, "Sat"), (22, "Sun")]:
            dt = _dt(2026, 3, day, 12, 0)
            assert format_rfc5322(dt).startswith(f"{name}, {day} Mar 2026")

    def test_month_names(self) -> None:
        dt = _dt(2026, 1, 5, 12, 0)  # January
        assert "Jan" in format_rfc5322(dt)
        dt = _dt(2026, 12, 1, 12, 0)  # December
        assert "Dec" in format_rfc5322(dt)


class TestBuildSendLaterHeaders:
    """Tests for build_send_later_headers."""

    def test_in_hours_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 10, 0)  # Monday in business hours
        assert build_send_later_headers(now) is None

    def test_before_hours_returns_none(self) -> None:
        now = _dt(2026, 3, 16, 7, 0)  # Monday before business hours
        assert build_send_later_headers(now) is None

    def test_weekend_schedules_monday(self) -> None:
        now = _dt(2026, 3, 15, 14, 0)  # Sunday
        headers = build_send_later_headers(now)
        assert headers is not None
        assert "Mon, 16 Mar 2026 08:00:00" in headers["X-Send-Later-At"]
        assert headers["X-Send-Later-Recur"] == "none"

    def test_evening_schedules_next_day(self) -> None:
        now = _dt(2026, 3, 16, 20, 0)  # Monday evening
        headers = build_send_later_headers(now)
        assert headers is not None
        assert "Tue, 17 Mar 2026 08:00:00" in headers["X-Send-Later-At"]
