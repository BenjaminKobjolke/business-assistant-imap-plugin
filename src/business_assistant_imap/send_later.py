"""Send Later header generation for Thunderbird Send Later extension.

Calculates the next business-hours send time and formats RFC 5322
headers that the Thunderbird Send Later extension uses to schedule
draft emails for delivery.
"""

from __future__ import annotations

from datetime import datetime, timedelta

DAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS_SHORT = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

HEADER_SEND_AT = "X-Send-Later-At"
HEADER_RECUR = "X-Send-Later-Recur"


def calculate_next_send_time(
    now: datetime,
    start_hour: int = 8,
    end_hour: int = 18,
) -> datetime | None:
    """Find the next business-hours send time, or ``None`` if already on track.

    Returns ``None`` on weekdays before or during business hours — the user
    will be at their desk soon (or already is), so no scheduling is needed
    and the draft should stay a normal draft for manual review.

    Returns a future datetime only when Send Later must hold the email:
    weekday evenings (after *end_hour*) and weekends.
    """
    weekday = now.weekday()  # Mon=0 .. Sun=6

    if weekday < 5 and now.hour < end_hour:
        # Weekday, before or during business hours → no scheduling needed.
        return None

    # After hours on a weekday, or weekend → advance to next business day.
    base = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    if weekday == 4:  # Friday after hours → Monday
        return base + timedelta(days=3)
    if weekday == 5:  # Saturday → Monday
        return base + timedelta(days=2)
    if weekday == 6:  # Sunday → Monday
        return base + timedelta(days=1)
    # Mon-Thu after hours → next day
    return base + timedelta(days=1)


def format_rfc5322(dt: datetime) -> str:
    """Format *dt* as an RFC 5322 date-time string.

    Example: ``Mon, 16 Mar 2026 08:00:00 +0100``

    The datetime **must** be timezone-aware so the UTC offset can be
    rendered correctly.
    """
    day_name = DAYS_SHORT[dt.weekday()]
    day = dt.day
    month = MONTHS_SHORT[dt.month - 1]
    year = dt.year
    time_str = f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"

    utc_offset = dt.utcoffset()
    if utc_offset is None:
        tz_str = "+0000"
    else:
        total_seconds = int(utc_offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        tz_str = f"{sign}{hours:02d}{minutes:02d}"

    return f"{day_name}, {day} {month} {year} {time_str} {tz_str}"


def build_send_later_headers(
    now: datetime,
    start_hour: int = 8,
    end_hour: int = 18,
) -> dict[str, str] | None:
    """Return custom headers dict for the Thunderbird Send Later extension.

    Returns ``None`` when no scheduling is needed (weekday daytime).
    Otherwise returns a dict with ``X-Send-Later-At`` and
    ``X-Send-Later-Recur``.
    """
    send_time = calculate_next_send_time(now, start_hour, end_hour)
    if send_time is None:
        return None
    return {
        HEADER_SEND_AT: format_rfc5322(send_time),
        HEADER_RECUR: "none",
    }
