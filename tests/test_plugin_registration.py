"""Tests for plugin registration."""

from __future__ import annotations

from unittest.mock import patch

from business_assistant.plugins.registry import PluginRegistry

from business_assistant_imap.plugin import register


class TestPluginRegistration:
    def test_register_skips_without_config(self, monkeypatch) -> None:
        monkeypatch.delenv("IMAP_SERVER", raising=False)
        registry = PluginRegistry()
        register(registry)
        assert registry.all_tools() == []

    @patch("business_assistant_imap.plugin.EmailService")
    def test_register_with_config(
        self, mock_service_cls, monkeypatch
    ) -> None:
        monkeypatch.setenv("IMAP_SERVER", "imap.example.com")
        monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
        monkeypatch.setenv("IMAP_PASSWORD", "password123")

        registry = PluginRegistry()
        register(registry)

        assert len(registry.all_tools()) == 16
        assert len(registry.plugins) == 1
        assert registry.plugins[0].name == "imap"
        assert registry.system_prompt_extras() != ""
