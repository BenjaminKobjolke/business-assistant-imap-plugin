"""Tests for EmailService core operations with mocked ImapClient."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.email_service import EmailService
from tests.conftest import FakeAttachment, FakeEmailMessage


class TestEmailService:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_inbox(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", subject="Test Email")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox()

        data = json.loads(result)
        assert len(data["emails"]) == 1
        assert data["emails"][0]["subject"] == "Test Email"
        assert data["emails"][0]["_id"] == "1"
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_messages(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX", "Company/Clients/Test",
        ]
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", subject="Folder Email")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_messages(
            folder="Company/Clients/Test", limit=10
        )

        data = json.loads(result)
        assert len(data["emails"]) == 1
        assert data["emails"][0]["subject"] == "Folder Email"
        mock_client.get_all_messages.assert_called_once_with(
            folder="Company/Clients/Test", limit=10
        )
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_messages_empty_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "EmptyFolder"]
        mock_client.get_all_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_messages(folder="EmptyFolder")

        assert "No emails found in EmptyFolder." in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_messages_folder_validation(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_messages(folder="nonexistent_folder")

        assert "not found" in result
        mock_client.get_all_messages.assert_not_called()

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
        mock_client.list_folders.return_value = [
            "INBOX", "Sent", "Drafts", "Trash",
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_folders()

        assert "INBOX" in result
        assert "Drafts" in result

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
                    to_address="bob@example.com",
                    cc_address="cc@example.com",
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.show_email("42", folder="Sent")

        data = json.loads(result)
        assert data["subject"] == "Hintergrundbilder"
        assert data["body"] == "Hier ist der Link."
        assert data["_id"] == "42"
        assert data["to"] == "bob@example.com"
        assert data["cc"] == "cc@example.com"
        assert data["attachments"] == []

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_server_side_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Server-side IMAP search returns results."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.return_value = [
            ("10", FakeEmailMessage(subject="Linux Update und SSO")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("Linux Update")

        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["subject"] == "Linux Update und SSO"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_fallback_client_side(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Server-side returns nothing — falls back to client-side."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.side_effect = [
            [],
            [
                (
                    "20",
                    FakeEmailMessage(
                        subject="Other",
                        body_plain="contains keyword here",
                    ),
                ),
                (
                    "21",
                    FakeEmailMessage(
                        subject="Unrelated",
                        body_plain="nothing relevant",
                    ),
                ),
            ],
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("keyword")

        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["_id"] == "20"
        assert mock_client.get_messages.call_count == 2

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_custom_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX", "Company/Clients/Test",
        ]
        mock_client.get_messages.return_value = [
            ("30", FakeEmailMessage(subject="AW: Linux Update und SSO")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails(
            "Linux Update", folder="Company/Clients/Test"
        )

        data = json.loads(result)
        assert len(data["results"]) == 1

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_no_matches(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.side_effect = [
            [],
            [
                (
                    "40",
                    FakeEmailMessage(
                        subject="Unrelated",
                        body_plain="nothing here",
                    ),
                ),
            ],
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("nonexistent")

        assert "No emails matching 'nonexistent' found." in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_empty_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "EmptyFolder"]
        mock_client.get_messages.side_effect = [[], []]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="EmptyFolder")

        assert "No emails found in EmptyFolder." in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_show_email_with_rich_attachment_metadata(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "50",
                FakeEmailMessage(
                    message_id="50",
                    subject="With Attachments",
                    to_address="recipient@example.com",
                    cc_address="cc1@example.com, cc2@example.com",
                    attachments=[
                        FakeAttachment(
                            filename="logo.png",
                            content_type="image/png",
                            data=b"\x89PNG" * 100,
                            content_id="cid-logo-123",
                            is_inline=True,
                        ),
                        FakeAttachment(
                            filename="report.pdf",
                            content_type="application/pdf",
                            data=b"%PDF" * 50,
                        ),
                    ],
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.show_email("50")

        data = json.loads(result)
        assert len(data["attachments"]) == 2
        assert data["attachments"][0]["filename"] == "logo.png"
        assert data["attachments"][0]["is_inline"] is True
        assert data["attachments"][1]["filename"] == "report.pdf"

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
