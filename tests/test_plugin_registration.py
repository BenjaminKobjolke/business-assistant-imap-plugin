"""Tests for plugin registration."""

from __future__ import annotations

from unittest.mock import patch

from business_assistant.plugins.registry import PluginRegistry

from business_assistant_imap.plugin import _extract_folder_from_query, register


class TestExtractFolderFromQuery:
    def test_folder_prefix_extracted(self) -> None:
        query, folder = _extract_folder_from_query("folder:produktstrategie linux", "INBOX")
        assert query == "linux"
        assert folder == "produktstrategie"

    def test_folder_prefix_case_insensitive(self) -> None:
        query, folder = _extract_folder_from_query("Folder:Sent updates", "INBOX")
        assert query == "updates"
        assert folder == "Sent"

    def test_no_prefix_unchanged(self) -> None:
        query, folder = _extract_folder_from_query("linux update", "INBOX")
        assert query == "linux update"
        assert folder == "INBOX"

    def test_explicit_folder_not_overridden(self) -> None:
        """If caller already set a non-INBOX folder, don't override it."""
        query, folder = _extract_folder_from_query(
            "folder:other search term", "Company/Projects"
        )
        assert query == "folder:other search term"
        assert folder == "Company/Projects"

    def test_multi_word_query_after_prefix(self) -> None:
        query, folder = _extract_folder_from_query("folder:Sent linux update sso", "INBOX")
        assert query == "linux update sso"
        assert folder == "Sent"

    def test_quoted_folder_with_spaces(self) -> None:
        query, folder = _extract_folder_from_query(
            'folder:"Company/Clients/Nürnberg Messe - Produktstrategie DeePS" linux', "INBOX"
        )
        assert query == "linux"
        assert folder == "Company/Clients/Nürnberg Messe - Produktstrategie DeePS"

    def test_quoted_folder_multi_word_query(self) -> None:
        query, folder = _extract_folder_from_query(
            'folder:"Company/Projects" linux update', "INBOX"
        )
        assert query == "linux update"
        assert folder == "Company/Projects"


class TestPluginRegistration:
    def test_register_skips_without_config(self, monkeypatch) -> None:
        monkeypatch.delenv("IMAP_SERVER", raising=False)
        registry = PluginRegistry()
        register(registry)
        assert registry.all_tools() == []

    @patch("business_assistant_imap.plugin.Database")
    @patch("business_assistant_imap.plugin.EmailService")
    def test_register_with_config(
        self, mock_service_cls, mock_db_cls, monkeypatch
    ) -> None:
        monkeypatch.setenv("IMAP_SERVER", "imap.example.com")
        monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
        monkeypatch.setenv("IMAP_PASSWORD", "password123")

        registry = PluginRegistry()
        register(registry)

        assert len(registry.all_tools()) == 23
        assert len(registry.plugins) == 1
        assert registry.plugins[0].name == "imap"
        assert registry.system_prompt_extras() != ""
