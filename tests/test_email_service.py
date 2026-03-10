"""Tests for EmailService with mocked ImapClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.email_service import EmailService, _extract_reply_address
from tests.conftest import FakeEmailMessage


class TestExtractReplyAddress:
    def test_with_angle_brackets(self) -> None:
        assert _extract_reply_address("Alice <alice@example.com>") == "alice@example.com"

    def test_plain_email(self) -> None:
        assert _extract_reply_address("alice@example.com") == "alice@example.com"

    def test_with_display_name(self) -> None:
        assert _extract_reply_address('"Alice Smith" <alice@example.com>') == "alice@example.com"


class TestEmailService:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_inbox(self, mock_client_cls: MagicMock, email_settings: EmailSettings) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", subject="Test Email")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox()

        assert "Test Email" in result
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_inbox_empty(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox()

        assert "No emails" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_unread_count(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            ("1", FakeEmailMessage()),
            ("2", FakeEmailMessage()),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.get_unread_count()

        assert "2" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_folders(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent", "Drafts", "Trash"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_folders()

        assert "INBOX" in result
        assert "Drafts" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "42",
                FakeEmailMessage(
                    to_address="alice@example.com",
                    subject="Hintergrundbilder",
                    date="Mon, 09 Mar 2026 14:30:00 +0100",
                    body_plain="Hallo Frau Schmidt, hier ist der Bericht.",
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_sent_to("alice@example.com")

        assert "alice@example.com" in result
        assert "Hallo Frau Schmidt" in result
        assert "[42]" in result
        assert "Subject: Hintergrundbilder" in result
        assert "Date: Mon, 09 Mar 2026" in result
        # Verify IMAP TO search was used
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["TO", "alice@example.com"],
            folder="Sent",
            limit=3,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to_no_matches(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_sent_to("alice@example.com")

        assert "No sent emails to alice@example.com" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_show_email_sent_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "42",
                FakeEmailMessage(
                    message_id="42",
                    subject="Hintergrundbilder",
                    body_plain="Hier ist der Link.",
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.show_email("42", folder="Sent")

        assert "Subject: Hintergrundbilder" in result
        assert "Hier ist der Link." in result
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["ALL"],
            folder="Sent",
            include_attachments=True,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_connection_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        with pytest.raises(ConnectionError):
            service.list_inbox()
