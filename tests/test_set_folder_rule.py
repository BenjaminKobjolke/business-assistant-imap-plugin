"""Tests for set_folder_rule tool wrapper."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from business_assistant_imap.plugin import _set_folder_rule


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.deps.plugin_data = {"database": MagicMock()}
    return ctx


class TestSetFolderRule:
    def test_person_rule(self) -> None:
        ctx = _make_ctx()
        result = _set_folder_rule(
            ctx, email_address="alice@example.com",
            target_folder="Clients/Alice", mapping_type="person",
        )
        data = json.loads(result)
        assert data["status"] == "created"
        assert data["identifier"] == "alice@example.com"
        assert data["target_folder"] == "Clients/Alice"
        assert data["mapping_type"] == "person"
        ctx.deps.plugin_data["database"].set_folder_mapping.assert_called_once_with(
            "alice@example.com", "Clients/Alice", "person",
        )

    def test_company_rule(self) -> None:
        ctx = _make_ctx()
        result = _set_folder_rule(
            ctx, email_address="bob@siemens.com",
            target_folder="Company/Siemens", mapping_type="company",
        )
        data = json.loads(result)
        assert data["identifier"] == "@siemens.com"
        assert data["mapping_type"] == "company"
        ctx.deps.plugin_data["database"].set_folder_mapping.assert_called_once_with(
            "@siemens.com", "Company/Siemens", "company",
        )

    def test_invalid_mapping_type(self) -> None:
        ctx = _make_ctx()
        result = _set_folder_rule(
            ctx, email_address="a@b.com",
            target_folder="X", mapping_type="invalid",
        )
        assert "Invalid mapping_type" in result

    def test_company_no_domain(self) -> None:
        ctx = _make_ctx()
        result = _set_folder_rule(
            ctx, email_address="nodomain",
            target_folder="X", mapping_type="company",
        )
        assert "Cannot determine domain" in result

    def test_person_lowercased(self) -> None:
        ctx = _make_ctx()
        _set_folder_rule(
            ctx, email_address="Alice@Example.COM",
            target_folder="X", mapping_type="person",
        )
        ctx.deps.plugin_data["database"].set_folder_mapping.assert_called_once_with(
            "alice@example.com", "X", "person",
        )
