"""Tests for meeting_parser module."""

from __future__ import annotations

from business_assistant_imap.meeting_parser import (
    extract_ics_data,
    extract_meeting_links,
    extract_meeting_times,
    parse_dt_field,
    parse_vevent,
)
from tests.conftest import SAMPLE_ICS, FakeAttachment, FakeEmailMessage


class TestParseVevent:
    def test_parse_valid_vevent(self) -> None:
        result = parse_vevent(SAMPLE_ICS)
        assert result is not None
        assert result["dtstart"] is not None
        assert result["dtend"] is not None
        assert result["organizer"] == "Alice Smith"
        assert "teams.microsoft.com" in (result["location"] or "")

    def test_parse_no_vevent(self) -> None:
        assert parse_vevent("no calendar data here") is None

    def test_parse_vevent_utc(self) -> None:
        ics = """\
BEGIN:VEVENT
DTSTART:20260315T100000Z
DTEND:20260315T110000Z
SUMMARY:UTC Meeting
END:VEVENT"""
        result = parse_vevent(ics)
        assert result is not None
        assert result["dtstart"].tzinfo is not None

    def test_parse_dt_field_with_tzid(self) -> None:
        text = "DTSTART;TZID=Europe/Berlin:20260315T100000"
        dt = parse_dt_field(text, "DTSTART")
        assert dt is not None
        assert dt.hour == 10

    def test_parse_dt_field_utc(self) -> None:
        text = "DTSTART:20260315T100000Z"
        dt = parse_dt_field(text, "DTSTART")
        assert dt is not None

    def test_parse_dt_field_missing(self) -> None:
        assert parse_dt_field("no field here", "DTSTART") is None


class TestExtractIcsData:
    def test_from_attachment(self) -> None:
        email = FakeEmailMessage(
            attachments=[
                FakeAttachment("invite.ics", "text/calendar", b"BEGIN:VCALENDAR")
            ]
        )
        assert extract_ics_data(email) == b"BEGIN:VCALENDAR"

    def test_no_ics_data(self) -> None:
        email = FakeEmailMessage()
        assert extract_ics_data(email) is None


class TestExtractMeetingTimes:
    def test_with_ics(self) -> None:
        email = FakeEmailMessage(
            attachments=[
                FakeAttachment("invite.ics", "text/calendar", SAMPLE_ICS.encode())
            ]
        )
        dtstart, dtend = extract_meeting_times(email)
        assert dtstart is not None
        assert dtend is not None

    def test_without_ics(self) -> None:
        email = FakeEmailMessage()
        dtstart, dtend = extract_meeting_times(email)
        assert dtstart is None
        assert dtend is None


class TestExtractMeetingLinks:
    def test_teams_link_from_ics(self) -> None:
        links = extract_meeting_links(FakeEmailMessage(), SAMPLE_ICS)
        types = [lnk["type"] for lnk in links]
        assert "Teams" in types

    def test_zoom_link_from_body(self) -> None:
        email = FakeEmailMessage(
            body_plain="Join: https://us02web.zoom.us/j/1234567890?pwd=abc"
        )
        links = extract_meeting_links(email, None)
        assert any(lnk["type"] == "Zoom" for lnk in links)

    def test_google_meet_link(self) -> None:
        email = FakeEmailMessage(
            body_plain="Meeting: https://meet.google.com/abc-defg-hij"
        )
        links = extract_meeting_links(email, None)
        assert any(lnk["type"] == "Google Meet" for lnk in links)

    def test_no_links(self) -> None:
        email = FakeEmailMessage(body_plain="No meeting links here.")
        links = extract_meeting_links(email, None)
        assert links == []

    def test_location_link_from_ics(self) -> None:
        ics = """\
BEGIN:VEVENT
DTSTART:20260315T100000Z
LOCATION:https://example.com/room
END:VEVENT"""
        links = extract_meeting_links(FakeEmailMessage(), ics)
        assert any(lnk["type"] == "Location link" for lnk in links)
