"""Tests for edit_draft service method."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from business_assistant_imap.config import EmailSettings, ImapSettings, SmtpSettings
from business_assistant_imap.email_service import EmailService
from tests.conftest import FakeEmailMessage


class TestEditDraft:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_edit_subject(self, mock_client_cls: MagicMock) -> None:
        """edit_draft replaces subject while keeping other fields."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="200",
            subject="Old Subject !2 ^tomorrow #project",
            from_address="user@example.com",
            to_address="delegate@example.com",
            body_html="<p>Original body</p>",
        )
        mock_client.get_message_by_id.return_value = ("200", fake_msg)
        mock_client.move_to_folder.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
        )
        service = EmailService(settings)
        result = service.edit_draft("200", subject="New Subject !2 ^tomorrow #project")

        assert result == "Compose draft saved."
        # Verify new draft has updated subject
        save_kwargs = mock_client.save_draft.call_args[1]
        assert save_kwargs["subject"] == "New Subject !2 ^tomorrow #project"
        assert save_kwargs["to_addresses"] == ["delegate@example.com"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_edit_body(self, mock_client_cls: MagicMock) -> None:
        """edit_draft replaces body while keeping subject."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="201",
            subject="Keep This Subject",
            to_address="bob@example.com",
            body_html="<p>Old body</p>",
        )
        mock_client.get_message_by_id.return_value = ("201", fake_msg)
        mock_client.move_to_folder.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
        )
        service = EmailService(settings)
        result = service.edit_draft("201", body="<p>New body</p>")

        assert result == "Compose draft saved."
        save_kwargs = mock_client.save_draft.call_args[1]
        assert save_kwargs["subject"] == "Keep This Subject"
        assert save_kwargs["body"] == "<p>New body</p>"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_not_found(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = None
        mock_client_cls.return_value = mock_client

        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
        )
        service = EmailService(settings)
        result = service.edit_draft("999")

        assert "not found" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_preserves_bcc(self, mock_client_cls: MagicMock) -> None:
        """edit_draft preserves BCC addresses from original draft."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="202",
            subject="Subject",
            to_address="alice@example.com",
            body_html="<p>Body</p>",
        )
        # Add BCC to raw message
        fake_msg.raw_message._headers["Bcc"] = "bcc@example.com"
        mock_client.get_message_by_id.return_value = ("202", fake_msg)
        mock_client.move_to_folder.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
        )
        service = EmailService(settings)
        service.edit_draft("202", subject="New Subject")

        save_kwargs = mock_client.save_draft.call_args[1]
        assert save_kwargs.get("bcc_addresses") == ["bcc@example.com"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_no_changes_keeps_original(self, mock_client_cls: MagicMock) -> None:
        """edit_draft with no overrides recreates the same draft."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="203",
            subject="Original",
            to_address="alice@example.com",
            body_html="<p>Original body</p>",
        )
        mock_client.get_message_by_id.return_value = ("203", fake_msg)
        mock_client.move_to_folder.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
        )
        service = EmailService(settings)
        result = service.edit_draft("203")

        assert result == "Compose draft saved."
        save_kwargs = mock_client.save_draft.call_args[1]
        assert save_kwargs["subject"] == "Original"
