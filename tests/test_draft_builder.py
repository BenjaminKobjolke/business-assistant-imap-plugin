"""Tests for draft_builder module."""

from __future__ import annotations

from business_assistant_imap.draft_builder import (
    DraftEmailContent,
    assemble_forward_html,
    assemble_reply_html,
    make_forward_subject,
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


class TestMakeForwardSubject:
    def test_adds_prefix(self) -> None:
        assert make_forward_subject("Hello") == "Fwd: Hello"

    def test_keeps_existing_prefix(self) -> None:
        assert make_forward_subject("Fwd: Hello") == "Fwd: Hello"

    def test_case_insensitive(self) -> None:
        assert make_forward_subject("FWD: Hello") == "FWD: Hello"


class TestAssembleForwardHtml:
    def test_basic_forward(self) -> None:
        html = assemble_forward_html(
            additional_message="FYI",
            original_from="alice@example.com",
            original_to="user@example.com",
            original_date="Mon, 10 Mar 2026 10:00:00",
            original_subject="Original Subject",
            original_body="Original body.",
        )
        assert "FYI" in html
        assert "Forwarded message" in html
        assert "alice@example.com" in html
        assert "user@example.com" in html
        assert "Original Subject" in html
        assert "Original body." in html

    def test_no_additional_message(self) -> None:
        html = assemble_forward_html(
            additional_message="",
            original_from="alice@example.com",
            original_to="user@example.com",
            original_date="Mon, 10 Mar 2026",
            original_subject="Test",
            original_body="Body.",
        )
        assert "Forwarded message" in html
        assert "Body." in html

    def test_forward_with_footer(self) -> None:
        footer = "<b>XIDA GmbH</b><br>09131 - 940 5 270"
        html = assemble_forward_html(
            additional_message="FYI",
            original_from="alice@example.com",
            original_to="user@example.com",
            original_date="Mon, 10 Mar 2026",
            original_subject="Test",
            original_body="Body.",
            footer_html=footer,
        )
        assert footer in html
        # Footer should appear before the HR / forwarded message block
        footer_pos = html.index(footer)
        hr_pos = html.index("Forwarded message")
        assert footer_pos < hr_pos

    def test_forward_without_footer(self) -> None:
        html = assemble_forward_html(
            additional_message="FYI",
            original_from="alice@example.com",
            original_to="user@example.com",
            original_date="Mon, 10 Mar 2026",
            original_subject="Test",
            original_body="Body.",
            footer_html="",
        )
        assert "margin-top: 20px" not in html


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

    def test_reply_with_footer(self) -> None:
        footer = "<b>XIDA GmbH</b><br>09131 - 940 5 270"
        content = DraftEmailContent(
            to_address="recipient@example.com",
            subject="Re: Test",
            greeting="Hi Bob",
            body_text="Thanks for your email.",
            original_from="bob@example.com",
            original_subject="Test",
            original_body="Original message here.",
        )
        html = assemble_reply_html(content, footer_html=footer)
        assert footer in html
        # Footer should appear between body and original message
        footer_pos = html.index(footer)
        original_pos = html.index("-----Original Message-----")
        assert footer_pos < original_pos

    def test_reply_without_footer(self) -> None:
        content = DraftEmailContent(
            to_address="recipient@example.com",
            subject="Re: Test",
            greeting="",
            body_text="Body text.",
            original_from="bob@example.com",
            original_subject="Test",
            original_body="Original.",
        )
        html = assemble_reply_html(content, footer_html="")
        assert "margin-top: 20px" not in html
