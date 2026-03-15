"""Tests for greeting_id token pattern in plugin wrappers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from business_assistant_imap.plugin import (
    _build_greeting,
    _compose_email,
    _greeting_registry,
    _reply_email,
    _resolve_greeting,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear greeting registry before each test."""
    _greeting_registry.clear()
    yield
    _greeting_registry.clear()


def _make_ctx(memory: dict[str, str] | None = None) -> MagicMock:
    """Create a mock RunContext with memory."""
    ctx = MagicMock()
    mem = MagicMock()
    mem.get.side_effect = lambda key, default="": (memory or {}).get(key, default)
    ctx.deps.memory = mem
    ctx.deps.plugin_data = {
        "email_service": MagicMock(),
        "email_database": MagicMock(),
    }
    return ctx


class TestResolveGreeting:
    def test_valid_id_returns_greeting(self) -> None:
        _greeting_registry["abc"] = "Hallo Herr Mueller"
        assert _resolve_greeting("abc") == "Hallo Herr Mueller"

    def test_valid_id_is_consumed(self) -> None:
        _greeting_registry["abc"] = "Hallo"
        _resolve_greeting("abc")
        assert "abc" not in _greeting_registry

    def test_invalid_id_returns_none(self) -> None:
        assert _resolve_greeting("nonexistent") is None

    def test_empty_id_returns_none(self) -> None:
        assert _resolve_greeting("") is None

    def test_single_use(self) -> None:
        _greeting_registry["abc"] = "Hallo"
        _resolve_greeting("abc")
        assert _resolve_greeting("abc") is None


class TestBuildGreeting:
    @patch("business_assistant_imap.plugin.build_greeting")
    def test_returns_json_with_id_and_greeting(self, mock_bg: MagicMock) -> None:
        mock_bg.return_value = "Hallo Herr Mueller"
        ctx = _make_ctx()
        result = json.loads(_build_greeting(ctx, salutation="Herr Mueller"))
        assert "greeting_id" in result
        assert result["greeting"] == "Hallo Herr Mueller"

    @patch("business_assistant_imap.plugin.build_greeting")
    def test_id_is_registered(self, mock_bg: MagicMock) -> None:
        mock_bg.return_value = "Hallo"
        ctx = _make_ctx()
        result = json.loads(_build_greeting(ctx))
        assert result["greeting_id"] in _greeting_registry

    @patch("business_assistant_imap.plugin.build_greeting")
    def test_salutation_disabled_returns_empty_greeting(
        self, mock_bg: MagicMock,
    ) -> None:
        ctx = _make_ctx({"pref:use_salutation": "false"})
        result = json.loads(_build_greeting(ctx, salutation="Herr Mueller"))
        assert result["greeting"] == ""
        assert result["greeting_id"] in _greeting_registry
        mock_bg.assert_not_called()

    @patch("business_assistant_imap.plugin.build_greeting")
    def test_salutation_enabled_calls_build_greeting(
        self, mock_bg: MagicMock,
    ) -> None:
        mock_bg.return_value = "Hallo Benjamin"
        ctx = _make_ctx({"pref:use_salutation": "true"})
        result = json.loads(_build_greeting(ctx, salutation="Benjamin"))
        assert result["greeting"] == "Hallo Benjamin"
        mock_bg.assert_called_once_with("Benjamin", formal=False)

    @patch("business_assistant_imap.plugin.build_greeting")
    def test_formal_greeting(self, mock_bg: MagicMock) -> None:
        mock_bg.return_value = "Sehr geehrter Herr Mueller"
        ctx = _make_ctx()
        result = json.loads(_build_greeting(ctx, salutation="Herr Mueller", formal=True))
        assert result["greeting"] == "Sehr geehrter Herr Mueller"
        mock_bg.assert_called_once_with("Herr Mueller", formal=True)

    @patch("business_assistant_imap.plugin.build_greeting")
    def test_default_pref_is_enabled(self, mock_bg: MagicMock) -> None:
        """When pref:use_salutation is not set, default is true."""
        mock_bg.return_value = "Hallo"
        ctx = _make_ctx()
        result = json.loads(_build_greeting(ctx))
        mock_bg.assert_called_once()
        assert result["greeting"] == "Hallo"


class TestReplyEmailGreetingId:
    def test_missing_greeting_id_returns_error(self) -> None:
        ctx = _make_ctx()
        result = _reply_email(ctx, email_id="1", reply_body="Thanks!")
        assert "Error" in result
        assert "build_greeting" in result

    def test_invalid_greeting_id_returns_error(self) -> None:
        ctx = _make_ctx()
        result = _reply_email(
            ctx, email_id="1", reply_body="Thanks!", greeting_id="bad-id",
        )
        assert "Error" in result

    @patch("business_assistant_imap.plugin._get_service")
    def test_valid_greeting_id_proceeds(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.draft_reply.return_value = "Draft reply saved."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["valid-id"] = "Hallo Herr Mueller"
        ctx = _make_ctx()
        result = _reply_email(
            ctx, email_id="1", reply_body="Thanks!", greeting_id="valid-id",
        )
        assert result == "Draft reply saved."
        mock_svc.draft_reply.assert_called_once_with(
            "1", "Thanks!", "Hallo Herr Mueller", "INBOX",
            include_footer=True,
        )

    @patch("business_assistant_imap.plugin._get_service")
    def test_empty_greeting_with_valid_id(self, mock_get_svc: MagicMock) -> None:
        """When salutation is disabled, greeting is empty but ID is valid."""
        mock_svc = MagicMock()
        mock_svc.draft_reply.return_value = "Draft reply saved."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["skip-id"] = ""
        ctx = _make_ctx()
        result = _reply_email(
            ctx, email_id="1", reply_body="Thanks!", greeting_id="skip-id",
        )
        assert result == "Draft reply saved."
        mock_svc.draft_reply.assert_called_once_with(
            "1", "Thanks!", "", "INBOX", include_footer=True,
        )

    @patch("business_assistant_imap.plugin._get_service")
    def test_send_action(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.send_reply.return_value = "Reply sent."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["send-id"] = "Hallo"
        ctx = _make_ctx()
        result = _reply_email(
            ctx, email_id="1", reply_body="Thanks!",
            greeting_id="send-id", action="send",
        )
        assert result == "Reply sent."
        mock_svc.send_reply.assert_called_once()


class TestComposeEmailGreetingId:
    def test_missing_greeting_id_returns_error(self) -> None:
        ctx = _make_ctx()
        result = _compose_email(
            ctx, to_addresses=["a@b.com"], subject="Hi", body="<p>Test</p>",
        )
        assert "Error" in result
        assert "build_greeting" in result

    @patch("business_assistant_imap.plugin._get_service")
    def test_valid_greeting_id_prepends_html(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.draft_compose.return_value = "Compose draft saved."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["g-id"] = "Hallo Benjamin"
        ctx = _make_ctx()
        result = _compose_email(
            ctx, to_addresses=["a@b.com"], subject="Hi",
            body="<p>Test</p>", greeting_id="g-id",
        )
        assert result == "Compose draft saved."
        call_kwargs = mock_svc.draft_compose.call_args[1]
        assert call_kwargs["body"].startswith(
            '<div style="margin-bottom: 10px;">Hallo Benjamin,</div>'
        )
        assert "<p>Test</p>" in call_kwargs["body"]

    @patch("business_assistant_imap.plugin._get_service")
    def test_valid_greeting_id_prepends_plain_text(
        self, mock_get_svc: MagicMock,
    ) -> None:
        mock_svc = MagicMock()
        mock_svc.draft_compose.return_value = "Compose draft saved."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["g-id"] = "Hallo"
        ctx = _make_ctx()
        result = _compose_email(
            ctx, to_addresses=["a@b.com"], subject="Hi",
            body="Test body", greeting_id="g-id", content_type="text/plain",
        )
        assert result == "Compose draft saved."
        call_kwargs = mock_svc.draft_compose.call_args[1]
        assert call_kwargs["body"].startswith("Hallo,\n\nTest body")

    @patch("business_assistant_imap.plugin._get_service")
    def test_empty_greeting_no_prepend(self, mock_get_svc: MagicMock) -> None:
        """Empty greeting (salutation disabled) does not prepend anything."""
        mock_svc = MagicMock()
        mock_svc.draft_compose.return_value = "Compose draft saved."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["empty-id"] = ""
        ctx = _make_ctx()
        result = _compose_email(
            ctx, to_addresses=["a@b.com"], subject="Hi",
            body="<p>Test</p>", greeting_id="empty-id",
        )
        assert result == "Compose draft saved."
        call_kwargs = mock_svc.draft_compose.call_args[1]
        assert call_kwargs["body"] == "<p>Test</p>"

    @patch("business_assistant_imap.plugin._get_service")
    def test_send_action(self, mock_get_svc: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc.compose_email.return_value = "Email sent to a@b.com."
        mock_get_svc.return_value = mock_svc

        _greeting_registry["s-id"] = "Hallo"
        ctx = _make_ctx()
        result = _compose_email(
            ctx, to_addresses=["a@b.com"], subject="Hi",
            body="<p>Test</p>", greeting_id="s-id", action="send",
        )
        assert result == "Email sent to a@b.com."
        mock_svc.compose_email.assert_called_once()
