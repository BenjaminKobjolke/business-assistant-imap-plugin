"""Tests for invite_handler module."""

from __future__ import annotations

from datetime import datetime

from business_assistant_imap.invite_handler import (
    ParsedInvite,
    build_rsvp_ics,
    build_rsvp_message,
    detect_invite,
    parse_invite_details,
)
from tests.conftest import SAMPLE_ICS, SAMPLE_ICS_CANCEL, FakeAttachment, FakeEmailMessage


class TestDetectInvite:
    def test_detect_invite_with_ics(self) -> None:
        email = FakeEmailMessage(
            attachments=[
                FakeAttachment("invite.ics", "text/calendar", SAMPLE_ICS.encode())
            ]
        )
        invite = detect_invite("123", email)
        assert invite is not None
        assert invite.summary == "Team Standup"
        assert invite.organizer_email is not None
        assert not invite.is_cancellation

    def test_detect_invite_no_ics(self) -> None:
        email = FakeEmailMessage()
        assert detect_invite("123", email) is None

    def test_detect_cancellation(self) -> None:
        email = FakeEmailMessage(
            attachments=[
                FakeAttachment("invite.ics", "text/calendar", SAMPLE_ICS_CANCEL.encode())
            ]
        )
        invite = detect_invite("456", email)
        assert invite is not None
        assert invite.is_cancellation


class TestParseInviteDetails:
    def test_parse_valid_ics(self) -> None:
        details = parse_invite_details(SAMPLE_ICS.encode())
        assert details.get("uid") == "test-uid-123@example.com"
        assert details.get("summary") == "Team Standup"
        assert details.get("method") == "REQUEST"

    def test_parse_cancel_ics(self) -> None:
        details = parse_invite_details(SAMPLE_ICS_CANCEL.encode())
        assert details.get("method") == "CANCEL"

    def test_parse_invalid_ics(self) -> None:
        details = parse_invite_details(b"not valid ics data")
        assert isinstance(details, dict)


class TestBuildRsvpIcs:
    def test_build_accepted(self) -> None:
        invite = ParsedInvite(
            message_id="1",
            subject="Meeting",
            ics_data=b"",
            uid="uid-123",
            summary="Team Standup",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=datetime(2026, 3, 15, 11, 0),
            organizer="Alice",
            organizer_email="alice@example.com",
            location=None,
            method="REQUEST",
        )
        ics = build_rsvp_ics(invite, "user@example.com", "ACCEPTED")
        assert "METHOD:REPLY" in ics
        assert "PARTSTAT=ACCEPTED" in ics
        assert "uid-123" in ics

    def test_build_declined(self) -> None:
        invite = ParsedInvite(
            message_id="1",
            subject="Meeting",
            ics_data=b"",
            uid="uid-123",
            summary="Meeting",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=None,
            organizer=None,
            organizer_email="org@example.com",
            location=None,
            method="REQUEST",
        )
        ics = build_rsvp_ics(invite, "user@example.com", "DECLINED")
        assert "PARTSTAT=DECLINED" in ics


class TestBuildRsvpMessage:
    def test_build_message(self) -> None:
        invite = ParsedInvite(
            message_id="1",
            subject="Meeting",
            ics_data=b"",
            uid="uid-123",
            summary="Team Standup",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=datetime(2026, 3, 15, 11, 0),
            organizer="Alice",
            organizer_email="alice@example.com",
            location=None,
            method="REQUEST",
        )
        msg = build_rsvp_message(invite, "user@example.com")
        assert msg["To"] == "alice@example.com"
        assert "Accepted" in msg["Subject"]
