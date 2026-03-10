"""Shared test fixtures for the IMAP plugin."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from business_assistant_imap.config import EmailSettings, ImapSettings, SmtpSettings

SAMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:test-uid-123@example.com
DTSTART;TZID=Europe/Berlin:20260315T100000
DTEND;TZID=Europe/Berlin:20260315T110000
SUMMARY:Team Standup
ORGANIZER;CN=Alice Smith:mailto:alice@example.com
LOCATION:https://teams.microsoft.com/l/meetup-join/abc123
X-MICROSOFT-SKYPETEAMSMEETINGURL:https://teams.microsoft.com/l/meetup-join/abc123
END:VEVENT
END:VCALENDAR"""

SAMPLE_ICS_CANCEL = """\
BEGIN:VCALENDAR
VERSION:2.0
METHOD:CANCEL
BEGIN:VEVENT
UID:cancel-uid-456@example.com
DTSTART:20260320T140000Z
DTEND:20260320T150000Z
SUMMARY:Cancelled Meeting
ORGANIZER;CN=Bob Jones:mailto:bob@example.com
END:VEVENT
END:VCALENDAR"""


@dataclass
class FakeAttachment:
    filename: str
    content_type: str
    data: bytes
    content_id: str | None = None
    is_inline: bool = False


class FakeRawMessage:
    """Minimal stand-in for email.message.Message."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers = headers or {}

    def get(self, key: str, default: str = "") -> str:
        return self._headers.get(key, default)


class FakeEmailMessage:
    """Fake email message for testing."""

    def __init__(
        self,
        message_id: str = "123",
        from_address: str = "sender@example.com",
        to_address: str = "",
        cc_address: str = "",
        subject: str = "Test Subject",
        date: str = "Mon, 15 Mar 2026 10:00:00 +0100",
        body_plain: str = "Hello, this is a test email.",
        body_html: str = "",
        attachments: list | None = None,
    ):
        self.message_id = message_id
        self.from_address = from_address
        self.subject = subject
        self.date = date
        self._body_plain = body_plain
        self._body_html = body_html
        self.attachments = attachments or []
        self.raw_message = FakeRawMessage({
            "To": to_address,
            "From": from_address,
            "Cc": cc_address,
        })

    def get_body(self, content_type: str = "text/plain") -> str | None:
        if content_type == "text/plain":
            return self._body_plain
        if content_type == "text/html":
            return self._body_html
        if content_type == "text/calendar":
            return None
        return None


@pytest.fixture()
def email_settings() -> EmailSettings:
    return EmailSettings(
        imap=ImapSettings(
            server="imap.example.com",
            username="user@example.com",
            password="password123",
        ),
        smtp=SmtpSettings(
            server="smtp.example.com",
            port=587,
            username="user@example.com",
            password="password123",
        ),
        from_address="user@example.com",
    )


@pytest.fixture()
def fake_email() -> FakeEmailMessage:
    return FakeEmailMessage()


@pytest.fixture()
def fake_email_with_ics() -> FakeEmailMessage:
    return FakeEmailMessage(
        attachments=[
            FakeAttachment(
                filename="invite.ics",
                content_type="text/calendar",
                data=SAMPLE_ICS.encode("utf-8"),
            )
        ],
    )
