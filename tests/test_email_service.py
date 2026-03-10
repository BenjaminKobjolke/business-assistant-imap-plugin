"""Tests for EmailService with mocked ImapClient."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.constants import FOLDER_NOT_FOUND_NO_SUGGESTIONS
from business_assistant_imap.email_service import EmailService, _extract_reply_address
from tests.conftest import FakeAttachment, FakeEmailMessage


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
        mock_client.list_folders.return_value = ["INBOX", "Company/Clients/Test"]
        mock_client.get_all_messages.return_value = [
            ("1", FakeEmailMessage(message_id="1", subject="Folder Email")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.list_messages(folder="Company/Clients/Test", limit=10)

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

        data = json.loads(result)
        assert len(data["sent_emails"]) == 1
        email = data["sent_emails"][0]
        assert email["_id"] == "42"
        assert email["subject"] == "Hintergrundbilder"
        assert "Mon, 09 Mar 2026" in email["date"]
        assert "Hallo Frau Schmidt" in email["body_snippet"]
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
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["ALL"],
            folder="Sent",
            include_attachments=True,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_server_side_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Server-side IMAP search returns results — no fallback needed."""
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
        # Should use server-side OR SUBJECT/FROM search
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["OR", "SUBJECT", "Linux Update", "FROM", "Linux Update"],
            folder="INBOX",
            limit=20,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_fallback_client_side(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Server-side returns nothing — falls back to client-side body filtering."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        # First call (server-side OR search) returns empty
        # Second call (ALL fallback) returns emails
        mock_client.get_messages.side_effect = [
            [],
            [
                ("20", FakeEmailMessage(subject="Other", body_plain="contains keyword here")),
                ("21", FakeEmailMessage(subject="Unrelated", body_plain="nothing relevant")),
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
        """Search in a custom folder passes the folder to IMAP."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Company/Clients/Test"]
        mock_client.get_messages.return_value = [
            ("30", FakeEmailMessage(subject="AW: Linux Update und SSO")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("Linux Update", folder="Company/Clients/Test")

        data = json.loads(result)
        assert len(data["results"]) == 1
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["OR", "SUBJECT", "Linux Update", "FROM", "Linux Update"],
            folder="Company/Clients/Test",
            limit=20,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_no_matches(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Both server-side and client-side find nothing."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_messages.side_effect = [
            [],
            [("40", FakeEmailMessage(subject="Unrelated", body_plain="nothing here"))],
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("nonexistent")

        assert "No emails matching 'nonexistent' found." in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_emails_empty_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Both server-side and fallback return empty — folder has no emails."""
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
        """show_email returns content_type, size, content_id, is_inline for attachments."""
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
        assert data["to"] == "recipient@example.com"
        assert data["cc"] == "cc1@example.com, cc2@example.com"
        assert len(data["attachments"]) == 2

        inline_att = data["attachments"][0]
        assert inline_att["filename"] == "logo.png"
        assert inline_att["content_type"] == "image/png"
        assert inline_att["size"] == 400
        assert inline_att["content_id"] == "cid-logo-123"
        assert inline_att["is_inline"] is True

        regular_att = data["attachments"][1]
        assert regular_att["filename"] == "report.pdf"
        assert regular_att["content_type"] == "application/pdf"
        assert regular_att["size"] == 200
        assert "content_id" not in regular_att
        assert "is_inline" not in regular_att

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """forward_email forwards the original message preserving attachments."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="90",
            subject="Original Subject",
            attachments=[
                FakeAttachment(
                    filename="image.png",
                    content_type="image/png",
                    data=b"imagedata",
                    content_id="cid-123",
                    is_inline=True,
                ),
            ],
        )
        mock_client.get_messages.return_value = [("90", fake_msg)]
        mock_client.forward_email.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email("90", ["helena@example.com"], "FYI")

        assert "forwarded to helena@example.com" in result
        mock_client.forward_email.assert_called_once_with(
            email_message=fake_msg,
            to_addresses=["helena@example.com"],
            sender_email="user@example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="user@example.com",
            smtp_password="password123",
            additional_message="FYI",
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """forward_email returns error when email ID not found."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email("999", ["helena@example.com"])

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """forward_email returns error when SMTP forward fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(message_id="91", subject="Test")
        mock_client.get_messages.return_value = [("91", fake_msg)]
        mock_client.forward_email.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email("91", ["bob@example.com"])

        assert result == "Failed to forward email."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """draft_forward saves a draft with attachments preserved."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        attachments = [
            FakeAttachment(
                filename="image.png",
                content_type="image/png",
                data=b"imagedata",
                content_id="cid-123",
                is_inline=True,
            ),
        ]
        fake_msg = FakeEmailMessage(
            message_id="100",
            subject="Original Subject",
            from_address="alice@example.com",
            to_address="user@example.com",
            body_plain="Original body text.",
            attachments=attachments,
        )
        mock_client.get_messages.return_value = [("100", fake_msg)]
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward("100", "helena@example.com", "FYI")

        assert result == "Forward draft saved."
        mock_client.save_draft.assert_called_once()
        call_kwargs = mock_client.save_draft.call_args[1]
        assert call_kwargs["to_addresses"] == ["helena@example.com"]
        assert call_kwargs["subject"] == "Fwd: Original Subject"
        assert call_kwargs["attachments"] == attachments
        assert "Forwarded message" in call_kwargs["body"]
        assert "alice@example.com" in call_kwargs["body"]
        assert "FYI" in call_kwargs["body"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """draft_forward returns error when email ID not found."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward("999", "helena@example.com")

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """draft_forward returns error when save_draft fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(message_id="101", subject="Test")
        mock_client.get_messages.return_value = [("101", fake_msg)]
        mock_client.save_draft.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward("101", "bob@example.com")

        assert result == "Failed to save forward draft."

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


class TestGetAttachmentUrl:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Uploads attachment via FTP and returns JSON with url."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "60",
                FakeEmailMessage(
                    message_id="60",
                    subject="With Attachment",
                    attachments=[
                        FakeAttachment(
                            filename="image.png",
                            content_type="image/png",
                            data=b"imagedata",
                        ),
                    ],
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        mock_ftp.upload.return_value = "https://cdn.example.com/abc_image.png"

        service = EmailService(email_settings)
        result = service.get_attachment_url("60", "image.png", ftp_service=mock_ftp)

        data = json.loads(result)
        assert data["filename"] == "image.png"
        assert data["url"] == "https://cdn.example.com/abc_image.png"
        assert data["content_type"] == "image/png"
        mock_ftp.upload.assert_called_once_with(b"imagedata", "image.png")

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Returns error when email ID is not found."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        service = EmailService(email_settings)
        result = service.get_attachment_url("999", "file.txt", ftp_service=mock_ftp)

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_attachment_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Returns error when filename doesn't match any attachment."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "70",
                FakeEmailMessage(
                    message_id="70",
                    subject="Other Attachment",
                    attachments=[
                        FakeAttachment(
                            filename="report.pdf",
                            content_type="application/pdf",
                            data=b"pdfdata",
                        ),
                    ],
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        service = EmailService(email_settings)
        result = service.get_attachment_url("70", "missing.txt", ftp_service=mock_ftp)

        assert result == "Attachment 'missing.txt' not found in email."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_no_ftp_service(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Returns error when FTP service is not configured."""
        service = EmailService(email_settings)
        result = service.get_attachment_url("60", "image.png")

        assert result == "FTP upload not configured."
        mock_client_cls.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_ftp_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Graceful error handling when FTP upload fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "80",
                FakeEmailMessage(
                    message_id="80",
                    subject="FTP Failure",
                    attachments=[
                        FakeAttachment(
                            filename="file.txt",
                            content_type="text/plain",
                            data=b"content",
                        ),
                    ],
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        mock_ftp.upload.side_effect = OSError("connection refused")

        service = EmailService(email_settings)
        result = service.get_attachment_url("80", "file.txt", ftp_service=mock_ftp)

        assert result == "FTP upload failed for 'file.txt'."


class TestFolderValidation:
    """Tests for _resolve_folder and its integration in search_emails."""

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_exact_match_proceeds(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Exact folder match — search proceeds normally."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent", "Company/Projects"]
        mock_client.get_messages.return_value = [
            ("1", FakeEmailMessage(subject="Match")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="Company/Projects")

        data = json.loads(result)
        assert len(data["results"]) == 1
        mock_client.get_messages.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_case_insensitive_match_resolves(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Case-insensitive match — resolves to server name."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent"]
        mock_client.get_messages.return_value = [
            ("1", FakeEmailMessage(subject="Match")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="inbox")

        data = json.loads(result)
        assert len(data["results"]) == 1
        # Should have searched with resolved folder name "INBOX"
        call_kwargs = mock_client.get_messages.call_args[1]
        assert call_kwargs["folder"] == "INBOX"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_substring_match_returns_error_with_suggestion(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Substring match — returns error with suggestion, get_messages NOT called."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX",
            "Company/Clients/Nürnberg Messe - Produktstrategie DeePS",
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("linux", folder="produktstrategie")

        assert "Folder 'produktstrategie' not found" in result
        assert "Nürnberg Messe - Produktstrategie DeePS" in result
        assert "list_folders" in result
        mock_client.get_messages.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_no_match_returns_error_no_suggestions(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """No match at all — returns error with 'Use list_folders' guidance."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent", "Drafts"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="zzz_nonexistent_zzz")

        expected = FOLDER_NOT_FOUND_NO_SUGGESTIONS.format(folder="zzz_nonexistent_zzz")
        assert result == expected
        mock_client.get_messages.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_folders_empty_skips_validation(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """list_folders() returns [] — validation skipped, search proceeds."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = []
        mock_client.get_messages.return_value = [
            ("1", FakeEmailMessage(subject="Match")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="AnyFolder")

        data = json.loads(result)
        assert len(data["results"]) == 1

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_multiple_substring_matches_limited(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """Multiple substring matches — all listed, up to MAX_FOLDER_SUGGESTIONS."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX",
            "Company/Clients/Alpha Project",
            "Company/Clients/Alpha Review",
            "Company/Clients/Alpha Budget",
            "Company/Clients/Alpha Extra",
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails("test", folder="alpha")

        assert "Folder 'alpha' not found" in result
        # Should list up to 3 suggestions
        assert result.count("Alpha") == 3
        mock_client.get_messages.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_default_inbox(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """move_email selects INBOX by default."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Archive"]
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email("42", "Archive")

        assert "moved to 'Archive'" in result
        mock_client.client.select_folder.assert_called_once_with("INBOX")
        mock_client.move_to_folder.assert_called_once_with("42", "Archive")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_custom_source_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """move_email selects the given source_folder before moving."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Company/@Meetings"]
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email("954", "INBOX", source_folder="Company/@Meetings")

        assert "moved to 'INBOX'" in result
        mock_client.client.select_folder.assert_called_once_with("Company/@Meetings")
        mock_client.move_to_folder.assert_called_once_with("954", "INBOX")

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_invalid_source_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        """move_email returns an error when source_folder doesn't exist."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Archive"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email("42", "Archive", source_folder="NonExistent")

        assert "not found" in result.lower()
        mock_client.move_to_folder.assert_not_called()

    @patch("business_assistant_imap.email_service.detect_invite")
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_detect_invite_includes_ics_data(
        self,
        mock_client_cls: MagicMock,
        mock_detect: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """detect_invite_in_email includes ics_data in the JSON response."""
        from datetime import datetime

        from business_assistant_imap.invite_handler import ParsedInvite
        from tests.conftest import SAMPLE_ICS

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
