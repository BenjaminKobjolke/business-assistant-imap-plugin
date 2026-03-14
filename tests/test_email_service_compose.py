"""Tests for EmailService compose operations (reply, forward, send)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from business_assistant_imap.config import EmailSettings, ImapSettings, SmtpSettings
from business_assistant_imap.email_service import EmailService
from business_assistant_imap.email_service_compose import (
    _extract_reply_address,
)
from tests.conftest import FakeAttachment, FakeEmailMessage


class TestExtractReplyAddress:
    def test_with_angle_brackets(self) -> None:
        assert (
            _extract_reply_address("Alice <alice@example.com>")
            == "alice@example.com"
        )

    def test_plain_email(self) -> None:
        assert (
            _extract_reply_address("alice@example.com")
            == "alice@example.com"
        )

    def test_with_display_name(self) -> None:
        assert (
            _extract_reply_address('"Alice Smith" <alice@example.com>')
            == "alice@example.com"
        )


class TestSearchSentTo:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
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
        assert "Hallo Frau Schmidt" in email["body_start"]
        assert email["body_end"] == ""
        mock_client.get_messages.assert_called_once_with(
            search_criteria=["TO", "alice@example.com"],
            folder="Sent",
            limit=3,
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to_no_matches(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_sent_to("alice@example.com")

        assert "No sent emails to alice@example.com" in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to_captures_sign_off(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """Body > 1000 chars produces body_end with sign-off."""
        long_body = "Hallo Frau Schmidt, " + ("lorem ipsum " * 100) + "Beste Grüße, Max"
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "43",
                FakeEmailMessage(
                    to_address="alice@example.com",
                    subject="Long email",
                    body_plain=long_body,
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_sent_to("alice@example.com")

        data = json.loads(result)
        email = data["sent_emails"][0]
        assert "Hallo Frau Schmidt" in email["body_start"]
        assert "Beste Grüße" in email["body_end"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_search_sent_to_medium_body_no_tail(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """Body ~800 chars (< 1000) produces empty body_end."""
        medium_body = "Hallo " + ("x" * 800) + " Ende"
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_messages.return_value = [
            (
                "44",
                FakeEmailMessage(
                    to_address="alice@example.com",
                    subject="Medium email",
                    body_plain=medium_body,
                ),
            ),
        ]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.search_sent_to("alice@example.com")

        data = json.loads(result)
        email = data["sent_emails"][0]
        assert email["body_start"] != ""
        assert email["body_end"] == ""


class TestComposeEmailWithFooter:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_compose_email_with_footer(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        """compose_email auto-appends footer when include_footer=True."""
        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
            footer_html="<p>My Footer</p>",
        )
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(settings)
        service.compose_email(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
        )

        call_kwargs = mock_client.send_email.call_args[1]
        assert "<p>My Footer</p>" in call_kwargs["body"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_compose_email_without_footer(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        """compose_email skips footer when include_footer=False."""
        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
            footer_html="<p>My Footer</p>",
        )
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(settings)
        service.compose_email(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
            include_footer=False,
        )

        call_kwargs = mock_client.send_email.call_args[1]
        assert "<p>My Footer</p>" not in call_kwargs["body"]


class TestDraftReplyWithoutFooter:
    @patch(
        "business_assistant_imap.email_service_compose.save_draft_to_imap"
    )
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_reply_without_footer(
        self,
        mock_client_cls: MagicMock,
        mock_save_draft: MagicMock,
    ) -> None:
        """draft_reply omits footer when include_footer=False."""
        settings = EmailSettings(
            imap=ImapSettings(server="imap.example.com", username="u", password="p"),
            smtp=SmtpSettings(server="smtp.example.com"),
            from_address="u@example.com",
            footer_html="<p>My Footer</p>",
        )
        mock_save_draft.return_value = True
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client_cls.return_value = mock_client

        service = EmailService(settings)
        service.draft_reply("1", "Thanks!", include_footer=False)

        call_kwargs = mock_save_draft.call_args[1]
        assert "<p>My Footer</p>" not in call_kwargs["html_body"]


class TestComposeEmail:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_compose_email_success(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.compose_email(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi there</p>",
        )

        assert "sent to alice@example.com" in result
        mock_client.send_email.assert_called_once()
        call_kwargs = mock_client.send_email.call_args[1]
        assert call_kwargs["to_addresses"] == ["alice@example.com"]
        assert call_kwargs["subject"] == "Hello"

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_compose_email_with_bcc(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.compose_email(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
            bcc_addresses=["bcc@example.com"],
        )

        assert "sent to alice@example.com" in result
        call_kwargs = mock_client.send_email.call_args[1]
        assert call_kwargs["bcc_addresses"] == ["bcc@example.com"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_compose_email_failure(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.send_email.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.compose_email(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
        )

        assert result == "Failed to send email."


class TestDraftCompose:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_compose_success(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_compose(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
        )

        assert result == "Compose draft saved."
        mock_client.save_draft.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_compose_with_bcc(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_compose(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
            bcc_addresses=["bcc@example.com"],
        )

        assert result == "Compose draft saved."
        call_kwargs = mock_client.save_draft.call_args[1]
        assert call_kwargs["bcc_addresses"] == ["bcc@example.com"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_compose_failure(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.save_draft.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_compose(
            to_addresses=["alice@example.com"],
            subject="Hello",
            body="<p>Hi</p>",
        )

        assert result == "Failed to save compose draft."


class TestForwardEmail:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_success(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """forward_email forwards preserving attachments."""
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
        mock_client.get_message_by_id.return_value = ("90", fake_msg)
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email(
            "90", ["helena@example.com"], "FYI"
        )

        assert "forwarded to helena@example.com" in result
        mock_client.send_email.assert_called_once()
        # Verify sent copy saved to Sent folder
        mock_client.save_draft.assert_called_once()
        sent_kwargs = mock_client.save_draft.call_args[1]
        assert sent_kwargs["draft_folder"] == "Sent"
        assert sent_kwargs["mark_as_unread"] is False

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_not_found(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = None
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email("999", ["helena@example.com"])

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_failure(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(message_id="91", subject="Test")
        mock_client.get_message_by_id.return_value = ("91", fake_msg)
        mock_client.send_email.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email("91", ["bob@example.com"])

        assert result == "Failed to forward email."
        mock_client.save_draft.assert_not_called()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_email_sent_copy_failure_still_succeeds(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """Forward succeeds even if saving to Sent folder fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="92", subject="Test Forward"
        )
        mock_client.get_message_by_id.return_value = ("92", fake_msg)
        mock_client.send_email.return_value = True
        mock_client.save_draft.side_effect = Exception("IMAP error")
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.forward_email(
            "92", ["bob@example.com"], "FYI"
        )

        assert "forwarded to bob@example.com" in result


class TestForwardEmailHtmlBody:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_prefers_html_body(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """forward_email preserves HTML formatting from original."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="95",
            subject="HTML Email",
            body_plain="Plain text fallback",
            body_html='<p style="color:red">Rich HTML</p>',
        )
        mock_client.get_message_by_id.return_value = ("95", fake_msg)
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.forward_email("95", ["bob@example.com"])

        call_kwargs = mock_client.send_email.call_args[1]
        assert '<p style="color:red">Rich HTML</p>' in call_kwargs["body"]
        assert "Plain text fallback" not in call_kwargs["body"]

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_forward_falls_back_to_plain_text(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """forward_email falls back to plain text when no HTML body."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(
            message_id="96",
            subject="Plain Email",
            body_plain="Line 1\nLine 2",
            body_html="",
        )
        mock_client.get_message_by_id.return_value = ("96", fake_msg)
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.forward_email("96", ["bob@example.com"])

        call_kwargs = mock_client.send_email.call_args[1]
        assert "Line 1<br>Line 2" in call_kwargs["body"]


class TestDraftForward:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_success(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
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
        mock_client.get_message_by_id.return_value = ("100", fake_msg)
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward(
            "100", "helena@example.com", "FYI"
        )

        assert result == "Forward draft saved."
        mock_client.save_draft.assert_called_once()
        call_kwargs = mock_client.save_draft.call_args[1]
        assert call_kwargs["to_addresses"] == ["helena@example.com"]
        assert call_kwargs["subject"] == "Fwd: Original Subject"
        assert call_kwargs["attachments"] == attachments

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_not_found(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = None
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward("999", "helena@example.com")

        assert result == "Email not found."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_forward_failure(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        fake_msg = FakeEmailMessage(message_id="101", subject="Test")
        mock_client.get_message_by_id.return_value = ("101", fake_msg)
        mock_client.save_draft.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.draft_forward("101", "bob@example.com")

        assert result == "Failed to save forward draft."


class TestDraftReplyFolder:
    @patch(
        "business_assistant_imap.email_service_compose.save_draft_to_imap"
    )
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_draft_reply_custom_folder(
        self,
        mock_client_cls: MagicMock,
        mock_save_draft: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """draft_reply uses the folder parameter."""
        mock_save_draft.return_value = True
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.draft_reply("1", "Thanks!", folder="Company/Projects")

        mock_client.get_message_by_id.assert_called_once_with(
            "1", folder="Company/Projects",
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_send_reply_custom_folder(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """send_reply uses the folder parameter."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.send_reply("1", "Thanks!", folder="Company/Projects")

        mock_client.get_message_by_id.assert_called_once_with(
            "1", folder="Company/Projects",
            include_attachments=False,
        )

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_send_reply_saves_to_sent_folder(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """send_reply saves a copy to the Sent folder after sending."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client.send_email.return_value = True
        mock_client.save_draft.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.send_reply("1", "Thanks!")

        assert result == "Reply sent."
        mock_client.save_draft.assert_called_once()
        sent_kwargs = mock_client.save_draft.call_args[1]
        assert sent_kwargs["draft_folder"] == "Sent"
        assert sent_kwargs["mark_as_unread"] is False

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_send_reply_sent_copy_failure_still_succeeds(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """send_reply succeeds even if saving to Sent folder fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client.send_email.return_value = True
        mock_client.save_draft.side_effect = Exception("IMAP error")
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.send_reply("1", "Thanks!")

        assert result == "Reply sent."

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_send_reply_failure_no_sent_copy(
        self,
        mock_client_cls: MagicMock,
        email_settings: EmailSettings,
    ) -> None:
        """send_reply does not save to Sent when send fails."""
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.get_message_by_id.return_value = (
            "1", FakeEmailMessage(message_id="1"),
        )
        mock_client.send_email.return_value = False
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.send_reply("1", "Thanks!")

        assert result == "Failed to send reply."
        mock_client.save_draft.assert_not_called()
