"""ICS/calendar parsing — extract meeting data from email messages.

Ported from imap-ai-assistant meeting_cleanup.py and meeting_display.py.
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, datetime

from dateutil.tz import UTC as DATEUTIL_UTC
from dateutil.tz import gettz

from .constants import MIME_TEXT_CALENDAR, MIME_TEXT_PLAIN

logger = logging.getLogger(__name__)


def extract_ics_data(email_message: object) -> bytes | None:
    """Extract raw ICS data from an email message.

    Strategy 1: Check attachments for text/calendar content type.
    Strategy 2: Fall back to text/calendar MIME part via get_body().
    """
    attachments = getattr(email_message, "attachments", []) or []
    for attachment in attachments:
        if attachment.content_type == MIME_TEXT_CALENDAR and attachment.data:
            return attachment.data

    try:
        calendar_text = email_message.get_body(MIME_TEXT_CALENDAR)
        if calendar_text:
            return calendar_text.encode("utf-8")
    except Exception:
        pass

    return None


def parse_dt_field(vevent_text: str, field: str) -> datetime | None:
    """Parse a DTSTART or DTEND field from a VEVENT text block."""
    m = re.search(rf"{field}(?:;([^:]*?))?[:]([^\r\n]+)", vevent_text)
    if not m:
        return None

    params, value = m.group(1) or "", m.group(2)

    tz = None
    tz_m = re.search(r"TZID=([^;:]+)", params)
    if tz_m:
        tz = gettz(tz_m.group(1))
    elif value.endswith("Z"):
        tz = DATEUTIL_UTC
        value = value[:-1]

    try:
        dt = (
            datetime.strptime(value, "%Y%m%dT%H%M%S")
            if "T" in value
            else datetime.strptime(value, "%Y%m%d")
        )
        dt = dt.replace(tzinfo=tz) if tz else dt.replace(tzinfo=DATEUTIL_UTC)
        return dt
    except ValueError as e:
        logger.warning("Failed to parse %s value '%s': %s", field, value, e)
        return None


def parse_vevent(ics_text: str) -> dict | None:
    """Parse VEVENT block from ICS text using regex.

    Returns dict with 'dtstart', 'dtend' (datetime), 'rrule' (str|None),
    'organizer' (str|None), 'location' (str|None), or None if parsing fails.
    """
    vevent_m = re.search(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.DOTALL)
    if not vevent_m:
        return None

    vevent = vevent_m.group(1)
    vevent = re.sub(r"\r?\n[ \t]", "", vevent)

    dtstart = parse_dt_field(vevent, "DTSTART")
    if dtstart is None:
        return None

    dtend = parse_dt_field(vevent, "DTEND")

    rrule = None
    rrule_m = re.search(r"RRULE[:]([^\r\n]+)", vevent)
    if rrule_m:
        rrule = rrule_m.group(1)

    organizer = None
    org_m = re.search(r"ORGANIZER[^:]*?CN=([^;:\r\n]+)", vevent)
    if org_m:
        organizer = org_m.group(1).strip().strip('"')

    location = None
    loc_m = re.search(r"LOCATION[:]([^\r\n]+)", vevent)
    if loc_m:
        location = loc_m.group(1).strip()

    return {
        "dtstart": dtstart,
        "dtend": dtend,
        "rrule": rrule,
        "organizer": organizer,
        "location": location,
    }


def normalize_to_utc(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def extract_meeting_times(
    email_message: object,
) -> tuple[datetime | None, datetime | None]:
    """Extract meeting start and end datetimes from ICS data.

    Returns (dtstart, dtend) as timezone-aware UTC datetimes, or (None, None).
    """
    ics_data = extract_ics_data(email_message)
    if ics_data is None:
        return None, None

    try:
        ics_text = ics_data.decode("utf-8", errors="replace")
        parsed = parse_vevent(ics_text)
        if parsed and parsed["dtstart"]:
            dtstart = normalize_to_utc(parsed["dtstart"])
            dtend = normalize_to_utc(parsed["dtend"]) if parsed.get("dtend") else None
            return dtstart, dtend
    except Exception as e:
        logger.warning("Failed to parse ICS data: %s", e)

    return None, None


def extract_meeting_links(
    email_message: object, ics_text: str | None
) -> list[dict[str, str]]:
    """Extract meeting URLs from ICS data and email body.

    Returns a list of dicts with 'type' and 'url' keys.
    Detects Teams, Zoom, and Google Meet links.
    """
    seen_urls: set[str] = set()
    links: list[dict[str, str]] = []

    _generic_paths = re.compile(
        r"^https://teams\.microsoft\.com/l/meetup-join/?$"
        r"|^https://teams\.microsoft\.com/?$"
        r"|^https://(?:[\w-]+\.)?zoom\.us/j/?$"
        r"|^https://meet\.google\.com/?$"
    )

    def _add(link_type: str, url: str) -> None:
        if url in seen_urls:
            return
        if _generic_paths.match(url):
            return
        seen_urls.add(url)
        links.append({"type": link_type, "url": url})

    if ics_text:
        skype_m = re.search(
            r"X-MICROSOFT-SKYPETEAMSMEETINGURL[:]([^\r\n]+)", ics_text
        )
        if skype_m:
            _add("Teams", skype_m.group(1).strip())

    body = ""
    with contextlib.suppress(Exception):
        body = email_message.get_body(MIME_TEXT_PLAIN) or ""

    url_patterns = [
        ("Teams", r'https://teams\.microsoft\.com/[^\s<>"]+'),
        ("Zoom", r'https://(?:[\w-]+\.)?zoom\.us/j/[^\s<>"]+'),
        ("Google Meet", r'https://meet\.google\.com/[^\s<>"]+'),
    ]
    for link_type, pattern in url_patterns:
        for m in re.finditer(pattern, body):
            _add(link_type, m.group(0))

    if ics_text:
        loc_m = re.search(r"LOCATION[:]([^\r\n]+)", ics_text)
        if loc_m:
            loc_val = loc_m.group(1).strip()
            if loc_val.startswith("http"):
                _add("Location link", loc_val)

    return links
