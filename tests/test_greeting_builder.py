"""Tests for greeting_builder module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from business_assistant_imap.greeting_builder import build_greeting


class TestBuildGreeting:
    def test_morning_with_salutation(self) -> None:
        with patch("business_assistant_imap.greeting_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15, 8, 30)
            assert build_greeting("Herr Mueller") == "Guten Morgen Herr Mueller"

    def test_afternoon_with_salutation(self) -> None:
        with patch("business_assistant_imap.greeting_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15, 14, 0)
            assert build_greeting("Benjamin") == "Hallo Benjamin"

    def test_boundary_at_10am(self) -> None:
        with patch("business_assistant_imap.greeting_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15, 10, 0)
            assert build_greeting("Frau Schmidt") == "Hallo Frau Schmidt"

    def test_morning_without_salutation(self) -> None:
        with patch("business_assistant_imap.greeting_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15, 9, 0)
            assert build_greeting() == "Guten Morgen"

    def test_afternoon_without_salutation(self) -> None:
        with patch("business_assistant_imap.greeting_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 15, 15, 0)
            assert build_greeting() == "Hallo"

    def test_skip_returns_empty(self) -> None:
        assert build_greeting("Herr Mueller", skip=True) == ""

    def test_skip_without_salutation(self) -> None:
        assert build_greeting(skip=True) == ""
