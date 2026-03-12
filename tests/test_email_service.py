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
        mock_client.list_folders.return_value = ["INBOX"]
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
        mock_client.list_folders.return_value = ["INBOX"]
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
    def test_search_emails_by_tag(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Search by IMAP keyword/tag returns matching emails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent"]
        mock_client.get_messages.return_value = [
            ("50", FakeEmailMessage(subject="Angebot Projekt X")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("", folder="Sent", tag="angebot")

        data = json.loads(result)
        assert len(data["results"]) == 1
        assert data["results"][0]["subject"] == "Angebot Projekt X"
        # Verify KEYWORD criteria was used
        call_args = mock_client.get_messages.call_args
        assert "KEYWORD" in call_args[1]["search_criteria"]
        assert "angebot" in call_args[1]["search_criteria"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_by_tag_with_query(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Search combining IMAP tag and text query."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.return_value = [
            ("60", FakeEmailMessage(subject="Invoice for ACME")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("ACME", tag="rechnung")

        data = json.loads(result)
        assert len(data["results"]) == 1
        criteria = mock_client.get_messages.call_args[1]["search_criteria"]
        assert "KEYWORD" in criteria
        assert "rechnung" in criteria
        assert "ACME" in criteria

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_by_tag_no_matches(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Tag search with no results skips client-side fallback."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("", tag="nonexistent")

        assert "No emails matching tag 'nonexistent' found." in result
        # Should NOT fall back to client-side (only 1 call)
        assert mock_client.get_messages.call_count == 1

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
    def test_list_inbox_unread_only(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.return_value = [
            ("5", FakeEmailMessage(message_id="5", subject="Unread Email")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox(unread_only=True)

        data = json.loads(result)
        assert len(data["emails"]) == 1
        assert data["emails"][0]["subject"] == "Unread Email"
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["UNSEEN"],
            folder="INBOX",
            limit=20,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_messages_unread_only(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent"]
        mock_client.get_messages.return_value = [
            ("10", FakeEmailMessage(message_id="10", subject="Unread Sent")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_messages(folder="Sent", unread_only=True)

        data = json.loads(result)
        assert len(data["emails"]) == 1
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["UNSEEN"],
            folder="Sent",
            limit=20,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_inbox_delegates_to_list_messages(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", subject="Test")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox(limit=5)

        data = json.loads(result)
        assert len(data["emails"]) == 1
        mock_client.get_all_messages.assert_called_once_with(
            folder="INBOX", limit=5
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_mark_as_read_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.mark_as_read.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.mark_as_read("42")

        assert result == "Email marked as read."
        mock_client.mark_as_read.assert_called_once_with("42")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_mark_as_read_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.mark_as_read.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.mark_as_read("42")

        assert result == "Failed to mark email as read."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_show_email_includes_tags(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "42",
                FakeEmailMessage(
                    message_id="42",
                    subject="Tagged Email",
                    keywords=["$label1", "important"],
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.show_email("42")

        data = json.loads(result)
        assert data["tags"] == ["$label1", "important"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_messages_includes_tags(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", keywords=["todo"])),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_inbox()

        data = json.loads(result)
        assert data["emails"][0]["tags"] == ["todo"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_email_tags_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_keywords.return_value = ["$label1", "important"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.get_email_tags("42")

        data = json.loads(result)
        assert data["email_id"] == "42"
        assert data["tags"] == ["$label1", "important"]
        mock_client.get_keywords.assert_called_once_with("42")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_email_tags_empty(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_keywords.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.get_email_tags("42")

        data = json.loads(result)
        assert data["tags"] == []

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_email_tags_invalid_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.get_email_tags("42", folder="nonexistent")

        assert "not found" in result
        mock_client.get_keywords.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_add_email_tag_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.add_keyword.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.add_email_tag("42", "$label1")

        assert result == "Tag '$label1' added to email."
        mock_client.add_keyword.assert_called_once_with("42", "$label1")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_add_email_tag_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.add_keyword.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.add_email_tag("42", "$label1")

        assert result == "Failed to add tag '$label1'."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_remove_email_tag_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.remove_keyword.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.remove_email_tag("42", "todo")

        assert result == "Tag 'todo' removed from email."
        mock_client.remove_keyword.assert_called_once_with("42", "todo")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_remove_email_tag_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.remove_keyword.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.remove_email_tag("42", "todo")

        assert result == "Failed to remove tag 'todo'."

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
