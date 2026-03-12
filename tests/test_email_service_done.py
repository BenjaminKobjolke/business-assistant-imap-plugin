"""Tests for the mark-as-done mixin (DoneMixin)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from business_assistant_imap.database import Database
from business_assistant_imap.email_service import EmailService


@pytest.fixture()
def db() -> Database:
    return Database(":memory:")


@pytest.fixture()
def service(email_settings: object) -> EmailService:
    return EmailService(email_settings)


def _mock_client_with_email(
    from_address: str = "sender@example.com",
    email_id: str = "100",
    message_id: str = "<test-123@example.com>",
) -> MagicMock:
    """Build a mock ImapClient that returns one email."""
    fake_msg = MagicMock()
    fake_msg.from_address = from_address
    fake_msg.raw_message = {"Message-ID": message_id}
    mock_client = MagicMock()
    mock_client.get_message_by_id.return_value = (str(email_id), fake_msg)
    mock_client.move_to_folder.return_value = True
    mock_client.client.select_folder = MagicMock()
    mock_client.client.search.return_value = [200]
    return mock_client


class TestMarkAsDoneKnownMapping:
    """Happy path — mapping already exists in DB."""

    def test_person_mapping_moves_email(self, service: EmailService, db: Database) -> None:
        db.set_folder_mapping("sender@example.com", "Clients/Sender", "person")
        mock_client = _mock_client_with_email()

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        data = json.loads(result)
        assert data["status"] == "done"
        assert data["moved_to"] == "Clients/Sender"
        assert data["new_email_id"] == "200"
        mock_client.move_to_folder.assert_called_once_with("100", "Clients/Sender")

    def test_company_mapping_moves_email(self, service: EmailService, db: Database) -> None:
        db.set_folder_mapping("@example.com", "Company/Example", "company")
        mock_client = _mock_client_with_email(from_address="anyone@example.com")

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        data = json.loads(result)
        assert data["status"] == "done"
        assert data["moved_to"] == "Company/Example"


class TestMarkAsDoneNoMapping:
    """No mapping exists, no target_folder provided."""

    def test_returns_error_with_sender(self, service: EmailService, db: Database) -> None:
        mock_client = _mock_client_with_email(from_address="new@unknown.org")

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        assert "No target folder configured for new@unknown.org" in result
        assert "target_folder" in result
        assert "mapping_type" in result


class TestMarkAsDoneWithTargetFolderNoType:
    """target_folder provided but no mapping_type."""

    def test_no_existing_mapping_returns_error(
        self, service: EmailService, db: Database
    ) -> None:
        mock_client = _mock_client_with_email()

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done(
                "100", database=db, target_folder="Clients/New"
            )

        assert "mapping_type" in result
        assert "person" in result
        assert "company" in result

    def test_existing_mapping_updates_folder(
        self, service: EmailService, db: Database
    ) -> None:
        db.set_folder_mapping("sender@example.com", "Old/Folder", "person")
        mock_client = _mock_client_with_email()

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done(
                "100", database=db, target_folder="New/Folder"
            )

        data = json.loads(result)
        assert data["status"] == "done"
        assert data["moved_to"] == "New/Folder"

        # Verify mapping was updated
        mapping = db.get_folder_mapping("sender@example.com")
        assert mapping is not None
        assert mapping.folder == "New/Folder"
        assert mapping.mapping_type == "person"  # kept original type


class TestMarkAsDoneWithTargetFolderAndType:
    """target_folder + mapping_type provided → store and move."""

    def test_person_mapping_stored_and_moved(
        self, service: EmailService, db: Database
    ) -> None:
        mock_client = _mock_client_with_email(from_address="alice@acme.com")

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done(
                "100",
                database=db,
                target_folder="Clients/Acme",
                mapping_type="person",
            )

        data = json.loads(result)
        assert data["status"] == "done"
        assert data["moved_to"] == "Clients/Acme"

        mapping = db.get_folder_mapping("alice@acme.com")
        assert mapping is not None
        assert mapping.identifier == "alice@acme.com"
        assert mapping.mapping_type == "person"

    def test_company_mapping_stored_and_moved(
        self, service: EmailService, db: Database
    ) -> None:
        mock_client = _mock_client_with_email(from_address="bob@siemens.com")

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done(
                "100",
                database=db,
                target_folder="Company/Siemens",
                mapping_type="company",
            )

        data = json.loads(result)
        assert data["status"] == "done"
        assert data["moved_to"] == "Company/Siemens"

        mapping = db.get_folder_mapping("bob@siemens.com")
        assert mapping is not None
        assert mapping.identifier == "@siemens.com"
        assert mapping.mapping_type == "company"

    def test_invalid_mapping_type(self, service: EmailService, db: Database) -> None:
        mock_client = _mock_client_with_email()

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done(
                "100",
                database=db,
                target_folder="Clients/X",
                mapping_type="invalid",
            )

        assert "Invalid mapping_type" in result


class TestMarkAsDoneLookupPriority:
    """Exact email match should win over domain match."""

    def test_person_wins_over_company(self, service: EmailService, db: Database) -> None:
        db.set_folder_mapping("@example.com", "Company/Example", "company")
        db.set_folder_mapping("vip@example.com", "VIP/Special", "person")
        mock_client = _mock_client_with_email(from_address="vip@example.com")

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        data = json.loads(result)
        assert data["moved_to"] == "VIP/Special"


class TestMarkAsDoneEdgeCases:
    def test_email_not_found(self, service: EmailService, db: Database) -> None:
        mock_client = MagicMock()
        mock_client.get_message_by_id.return_value = None

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("999", database=db)

        assert result == "Email not found."

    def test_from_header_with_display_name(
        self, service: EmailService, db: Database
    ) -> None:
        """Sender like 'Alice Smith <alice@acme.com>' should extract the email."""
        db.set_folder_mapping("alice@acme.com", "Clients/Acme", "person")
        mock_client = _mock_client_with_email(
            from_address="Alice Smith <alice@acme.com>"
        )

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        data = json.loads(result)
        assert data["moved_to"] == "Clients/Acme"

    def test_move_failure(self, service: EmailService, db: Database) -> None:
        db.set_folder_mapping("sender@example.com", "Clients/X", "person")
        mock_client = _mock_client_with_email()
        mock_client.move_to_folder.return_value = False

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db)

        assert "Failed to move" in result

    def test_custom_source_folder(self, service: EmailService, db: Database) -> None:
        db.set_folder_mapping("sender@example.com", "Archive/Done", "person")
        mock_client = _mock_client_with_email()

        with patch.object(service, "_create_client", return_value=mock_client):
            result = service.mark_as_done("100", database=db, folder="Work/Pending")

        mock_client.get_message_by_id.assert_called_once_with(
            "100",
            folder="Work/Pending",
            include_attachments=False,
        )
        # select_folder called twice: source before move, destination for UID lookup
        calls = mock_client.client.select_folder.call_args_list
        assert calls[0].args == ("Work/Pending",)
        assert calls[1].args == ("Archive/Done",)
        data = json.loads(result)
        assert data["moved_to"] == "Archive/Done"
        assert data["new_email_id"] == "200"
