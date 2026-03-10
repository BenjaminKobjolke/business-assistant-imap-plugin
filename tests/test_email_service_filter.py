"""Tests for EmailService.filter_emails."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from business_assistant_imap.config import EmailSettings
from business_assistant_imap.constants import (
    FILTER_INVALID_ACTION,
    FILTER_INVALID_REGEX,
    FILTER_MOVE_NO_DESTINATION,
    FILTER_NO_PATTERN,
)
from business_assistant_imap.email_service import EmailService
from tests.conftest import FakeEmailMessage


def _make_messages(items: list[tuple[str, str, str]]) -> list[tuple[str, FakeEmailMessage]]:
    """Build a list of (msg_id, FakeEmailMessage) from (id, subject, from) tuples."""
    return [
        (mid, FakeEmailMessage(message_id=mid, subject=subj, from_address=frm))
        for mid, subj, frm in items
    ]


class TestFilterEmails:
    @patch("business_assistant_imap.email_service.ImapClient")
    def test_dry_run_matches_subject(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Newsletter March", "news@example.com"),
            ("2", "Important meeting", "boss@example.com"),
            ("3", "Weekly Newsletter", "news@example.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="newsletter", dry_run=True)

        data = json.loads(result)
        assert data["dry_run"] is True
        assert data["matched"] == 2
        assert data["total_scanned"] == 3
        assert data["results"][0]["subject"] == "Newsletter March"
        assert data["results"][1]["subject"] == "Weekly Newsletter"
        mock_client.move_to_folder.assert_not_called()
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_dry_run_matches_from(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Hello", "spam@junk.com"),
            ("2", "Meeting", "boss@work.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(from_pattern="junk\\.com", dry_run=True)

        data = json.loads(result)
        assert data["matched"] == 1
        assert data["results"][0]["from"] == "spam@junk.com"
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_dry_run_matches_both_patterns(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Newsletter", "news@example.com"),
            ("2", "Newsletter", "boss@work.com"),
            ("3", "Meeting", "news@example.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(
            subject_pattern="newsletter", from_pattern="news@", dry_run=True
        )

        data = json.loads(result)
        assert data["matched"] == 1
        assert data["results"][0]["_id"] == "1"
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_no_matches(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Meeting notes", "boss@work.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="newsletter", dry_run=True)

        data = json.loads(result)
        assert data["matched"] == 0
        assert data["total_scanned"] == 1
        assert data["results"] == []
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_empty_folder(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = []
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="test", dry_run=True)

        data = json.loads(result)
        assert data["matched"] == 0
        assert data["total_scanned"] == 0
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_trash_action_dry_run_false(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Spam offer", "spam@junk.com"),
            ("2", "Real email", "boss@work.com"),
        ])
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(
            subject_pattern="spam", action="trash", dry_run=False
        )

        data = json.loads(result)
        assert data["dry_run"] is False
        assert data["matched"] == 1
        mock_client.client.select_folder.assert_called_once_with("INBOX")
        mock_client.move_to_folder.assert_called_once_with("1", "Trash")
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_move_action_dry_run_false(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Project update", "team@work.com"),
            ("2", "Other email", "boss@work.com"),
        ])
        mock_client.move_to_folder.return_value = True
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(
            subject_pattern="project",
            action="move",
            destination="Archive",
            dry_run=False,
        )

        data = json.loads(result)
        assert data["dry_run"] is False
        assert data["matched"] == 1
        mock_client.move_to_folder.assert_called_once_with("1", "Archive")
        mock_client.disconnect.assert_called_once()

    def test_no_pattern_returns_error(self, email_settings: EmailSettings) -> None:
        service = EmailService(email_settings)
        result = service.filter_emails()

        assert result == FILTER_NO_PATTERN

    def test_invalid_action_returns_error(self, email_settings: EmailSettings) -> None:
        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="test", action="delete")

        assert result == FILTER_INVALID_ACTION.format(action="delete")

    def test_move_without_destination_returns_error(
        self, email_settings: EmailSettings
    ) -> None:
        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="test", action="move")

        assert result == FILTER_MOVE_NO_DESTINATION

    def test_invalid_regex_returns_error(self, email_settings: EmailSettings) -> None:
        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="[invalid")

        assert FILTER_INVALID_REGEX.format(error="").split(":")[0] in result

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_case_insensitive_matching(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "NEWSLETTER UPDATE", "news@example.com"),
            ("2", "newsletter digest", "news@example.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(subject_pattern="Newsletter", dry_run=True)

        data = json.loads(result)
        assert data["matched"] == 2
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_custom_folder_and_limit(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Archive"]
        mock_client.get_all_messages.return_value = _make_messages([
            ("1", "Old email", "old@example.com"),
        ])
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        service.filter_emails(
            subject_pattern="old", folder="Archive", limit=10, dry_run=True
        )

        mock_client.get_all_messages.assert_called_once_with(folder="Archive", limit=10)
        mock_client.disconnect.assert_called_once()

    @patch("business_assistant_imap.email_service.ImapClient")
    def test_folder_validation(
        self, mock_client_cls: MagicMock, email_settings: EmailSettings
    ) -> None:
        mock_client = MagicMock()
        mock_client.connect.return_value = True
        mock_client.list_folders.return_value = ["INBOX", "Sent"]
        mock_client_cls.return_value = mock_client

        service = EmailService(email_settings)
        result = service.filter_emails(
            subject_pattern="test", folder="NonExistent", dry_run=True
        )

        assert "not found" in result.lower()
        mock_client.disconnect.assert_called_once()
