"""Tests for draft_builder module."""

from __future__ import annotations

from business_assistant_imap.draft_builder import (
    DraftEmailContent,
    assemble_reply_html,
    make_reply_subject,
)


class TestMakeReplySubject:
    def test_adds_prefix(self) -> None:
        assert make_reply_subject("Hello") == "Re: Hello"

    def test_keeps_existing_prefix(self) -> None:
        assert make_reply_subject("Re: Hello") == "Re: Hello"

    def test_case_insensitive(self) -> None:
        assert make_reply_subject("RE: Hello") == "RE: Hello"

    def test_re_prefix_case(self) -> None:
        assert make_reply_subject("re: lowercase") == "re: lowercase"


class TestAssembleReplyHtml:
    def test_basic_reply(self) -> None:
        content = DraftEmailContent(
            to_address="recipient@example.com",
            subject="Re: Test",
            greeting="Hi Bob",
            body_text="Thanks for your email.",
            original_from="bob@example.com",
            original_subject="Test",
            original_body="Original message here.",
        )
        html = assemble_reply_html(content)
        assert "Hi Bob" in html
        assert "Thanks for your email." in html
        assert "Original message here." in html
        assert "-----Original Message-----" in html

    def test_no_greeting(self) -> None:
        content = DraftEmailContent(
            to_address="recipient@example.com",
            subject="Re: Test",
            greeting="",
            body_text="Body text.",
            original_from="bob@example.com",
            original_subject="Test",
            original_body="Original.",
        )
        html = assemble_reply_html(content)
        assert "Body text." in html
        assert "margin-bottom: 10px" not in html

    def test_newlines_to_br(self) -> None:
        content = DraftEmailContent(
            to_address="recipient@example.com",
            subject="Re: Test",
            greeting="",
            body_text="Line 1\nLine 2",
            original_from="bob@example.com",
            original_subject="Test",
            original_body="Orig line 1\nOrig line 2",
        )
        html = assemble_reply_html(content)
        assert "Line 1<br>Line 2" in html
        assert "Orig line 1<br>Orig line 2" in html
