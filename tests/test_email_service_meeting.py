"""Tests for EmailService meeting/invite operations."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.email_service import EmailService
from business_assistant_imap.invite_handler import ParsedInvite
from tests.conftest import SAMPLE_ICS, FakeEmailMessage


class TestMeetingOperations:
    @patch("business_assistant_imap.email_service_meeting.detect_invite")
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_detect_invite_includes_ics_data(
        self,
        mock_client_cls: MagicMock,
        mock_detect: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """detect_invite_in_email includes ics_data in the JSON response."""
        ics_bytes = SAMPLE_ICS.encode("utf-8")
        invite = ParsedInvite(
            message_id="1",
            subject="Team Standup",
            ics_data=ics_bytes,
            uid="test-uid-123@example.com",
            summary="Team Standup",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=datetime(2026, 3, 15, 11, 0),
            organizer="Alice Smith",
            organizer_email="alice@example.com",
            location="https://teams.microsoft.com/l/meetup-join/abc123",
            method="REQUEST",
        )
        mock_detect.return_value = invite

        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.detect_invite_in_email("1")

        data = json.loads(result)
        assert "ics_data" in data
        assert data["ics_data"].startswith("BEGIN:VCALENDAR")
        assert "VEVENT" in data["ics_data"]
        assert data["subject"] == "Team Standup"

    @patch("business_assistant_imap.email_service_meeting.detect_invite")
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_detect_invite_sanitizes_null_bytes(
        self,
        mock_client_cls: MagicMock,
        mock_detect: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """ICS data with embedded null bytes should be sanitized."""
        ics_with_nulls = (
            b"\x00"
            + SAMPLE_ICS.encode("utf-8").replace(
                b"VEVENT", b"V\x00EVENT"
            )
        )
        invite = ParsedInvite(
            message_id="1",
            subject="Team Standup",
            ics_data=ics_with_nulls,
            uid="test-uid-123@example.com",
            summary="Team Standup",
            dtstart=datetime(2026, 3, 15, 10, 0),
            dtend=datetime(2026, 3, 15, 11, 0),
            organizer="Alice Smith",
            organizer_email="alice@example.com",
            location="Conference Room A",
            method="REQUEST",
        )
        mock_detect.return_value = invite

        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.detect_invite_in_email("1")

        data = json.loads(result)
        assert "ics_data" in data
        assert "\x00" not in data["ics_data"]
        assert "VEVENT" in data["ics_data"]

    @patch(
        "business_assistant_imap.email_service_meeting.extract_meeting_times"
    )
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_meeting_info_custom_folder(
        self,
        mock_client_cls: MagicMock,
        mock_extract: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """get_meeting_info uses the folder parameter."""
        mock_extract.return_value = (None, None)
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.get_meeting_info("1", folder="Company/Meetings")

        mock_client.get_all_messages.assert_called_once_with(
            folder="Company/Meetings"
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_meeting_links_custom_folder(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """get_meeting_links uses the folder parameter."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.get_meeting_links("1", folder="Company/Meetings")

        mock_client.get_all_messages.assert_called_once_with(
            folder="Company/Meetings"
        )

    @patch("business_assistant_imap.email_service_meeting.detect_invite")
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_detect_invite_custom_folder(
        self,
        mock_client_cls: MagicMock,
        mock_detect: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """detect_invite_in_email uses the folder parameter."""
        mock_detect.return_value = None
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.detect_invite_in_email("1", folder="Archive")

        mock_client.get_all_messages.assert_called_once_with(
            folder="Archive"
        )

    @patch("business_assistant_imap.email_service_meeting.detect_invite")
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_send_rsvp_custom_folder(
        self,
        mock_client_cls: MagicMock,
        mock_detect: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """send_rsvp_for_email uses the folder parameter."""
        mock_detect.return_value = None
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.send_rsvp_for_email("1", folder="Archive")

        mock_client.get_all_messages.assert_called_once_with(
            folder="Archive"
        )
