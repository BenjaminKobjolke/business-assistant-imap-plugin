"""Tests for EmailService attachment and folder validation operations."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.constants import FOLDER_NOT_FOUND_NO_SUGGESTIONS
from business_assistant_imap.email_service import EmailService
from tests.conftest import FakeAttachment, FakeEmailMessage


class TestGetAttachmentUrl:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_success(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
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
        )
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        mock_ftp.upload.return_value = (
            "https://cdn.example.com/abc_image.png"
        )

        service = EmailService(email_settings)
        result = service.get_attachment_url(
            "60", "image.png", ftp_service=mock_ftp
        )

        data = json.loads(result)
        assert data["filename"] == "image.png"
        assert data["content_type"] == "image/png"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = None
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        service = EmailService(email_settings)
        result = service.get_attachment_url(
            "999", "file.txt", ftp_service=mock_ftp
        )

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_attachment_not_found(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
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
        )
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        service = EmailService(email_settings)
        result = service.get_attachment_url(
            "70", "missing.txt", ftp_service=mock_ftp
        )

        assert "not found in email" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_no_ftp_service(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        service = EmailService(email_settings)
        result = service.get_attachment_url("60", "image.png")

        assert result == "FTP upload not configured."
        mock_client_cls.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_get_attachment_url_ftp_failure(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
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
        )
        mock_client_cls.return_value = mock_client

        mock_ftp = MagicMock()
        mock_ftp.upload.side_effect = OSError("connection refused")

        service = EmailService(email_settings)
        result = service.get_attachment_url(
            "80", "file.txt", ftp_service=mock_ftp
        )

        assert result == "FTP upload failed for 'file.txt'."


class TestFolderValidation:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_exact_match_proceeds(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX", "Sent", "Company/Projects",
        ]
        mock_client.get_messages.return_value = [
            ("1", FakeEmailMessage(subject="Match")),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails(
            "test", folder="Company/Projects"
        )

        data = json.loads(result)
        assert len(data["results"]) == 1

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_case_insensitive_match_resolves(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
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
        call_kwargs = mock_client.get_messages.call_args[1]
        assert call_kwargs["folder"] == "INBOX"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_substring_match_returns_error_with_suggestion(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX",
            "Company/Clients/Nürnberg Messe - Produktstrategie DeePS",
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails(
            "linux", folder="produktstrategie"
        )

        assert "Folder 'produktstrategie' not found" in result
        assert "Produktstrategie DeePS" in result
        mock_client.get_messages.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_no_match_returns_error_no_suggestions(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX", "Sent", "Drafts",
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_emails(
            "test", folder="zzz_nonexistent_zzz"
        )

        expected = FOLDER_NOT_FOUND_NO_SUGGESTIONS.format(
            folder="zzz_nonexistent_zzz"
        )
        assert result == expected

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_list_folders_empty_skips_validation(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
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
        assert result.count("Alpha") == 3
        mock_client.get_messages.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_default_inbox(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Archive"]
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email("42", "Archive")

        assert "moved to 'Archive'" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_custom_source_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = [
            "INBOX", "Company/@Meetings",
        ]
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email(
            "954", "INBOX", source_folder="Company/@Meetings"
        )

        assert "moved to 'INBOX'" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_email_invalid_source_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Archive"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.move_email(
            "42", "Archive", source_folder="NonExistent"
        )

        assert "not found" in result.lower()
        mock_client.move_to_folder.assert_not_called()
