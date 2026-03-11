"""Tests for the SQLAlchemy-based folder-mapping database."""

from __future__ import annotations

import pytest

from business_assistant_imap.database import Database, FolderMapping


@pytest.fixture()
def db() -> Database:
    """Create an in-memory database for testing."""
    database = Database(":memory:")
    return database


class TestFolderMappingModel:
    def test_model_attributes(self) -> None:
        mapping = FolderMapping(
            identifier="user@example.com",
            folder="Company/Clients/Acme",
            mapping_type="person",
        )
        assert mapping.identifier == "user@example.com"
        assert mapping.folder == "Company/Clients/Acme"
        assert mapping.mapping_type == "person"


class TestGetFolderMapping:
    def test_exact_email_match(self, db: Database) -> None:
        db.set_folder_mapping("alice@example.com", "Clients/Alice", "person")
        result = db.get_folder_mapping("alice@example.com")
        assert result is not None
        assert result.folder == "Clients/Alice"
        assert result.mapping_type == "person"

    def test_domain_match(self, db: Database) -> None:
        db.set_folder_mapping("@example.com", "Company/Example", "company")
        result = db.get_folder_mapping("anyone@example.com")
        assert result is not None
        assert result.folder == "Company/Example"
        assert result.mapping_type == "company"

    def test_no_match(self, db: Database) -> None:
        result = db.get_folder_mapping("unknown@nowhere.org")
        assert result is None

    def test_exact_match_wins_over_domain(self, db: Database) -> None:
        db.set_folder_mapping("@siemens.com", "Company/Siemens", "company")
        db.set_folder_mapping("vip@siemens.com", "Company/Siemens/VIP", "person")
        result = db.get_folder_mapping("vip@siemens.com")
        assert result is not None
        assert result.folder == "Company/Siemens/VIP"
        assert result.identifier == "vip@siemens.com"

    def test_case_insensitive_lookup(self, db: Database) -> None:
        db.set_folder_mapping("Alice@Example.COM", "Clients/Alice", "person")
        result = db.get_folder_mapping("alice@example.com")
        assert result is not None
        assert result.folder == "Clients/Alice"


class TestSetFolderMapping:
    def test_insert_new(self, db: Database) -> None:
        db.set_folder_mapping("bob@test.com", "Clients/Bob", "person")
        result = db.get_folder_mapping("bob@test.com")
        assert result is not None
        assert result.folder == "Clients/Bob"

    def test_upsert_updates_existing(self, db: Database) -> None:
        db.set_folder_mapping("bob@test.com", "Clients/Bob", "person")
        db.set_folder_mapping("bob@test.com", "Clients/Bob-New", "person")
        result = db.get_folder_mapping("bob@test.com")
        assert result is not None
        assert result.folder == "Clients/Bob-New"

    def test_upsert_changes_type(self, db: Database) -> None:
        db.set_folder_mapping("@test.com", "Company/Test", "company")
        db.set_folder_mapping("@test.com", "Company/TestNew", "person")
        result = db.get_folder_mapping("anyone@test.com")
        assert result is not None
        assert result.folder == "Company/TestNew"
        assert result.mapping_type == "person"

    def test_identifier_stored_lowercase(self, db: Database) -> None:
        db.set_folder_mapping("Alice@EXAMPLE.com", "Clients/Alice", "person")
        result = db.get_folder_mapping("alice@example.com")
        assert result is not None
        assert result.identifier == "alice@example.com"
