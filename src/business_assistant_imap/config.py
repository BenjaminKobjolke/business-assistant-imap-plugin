"""IMAP and SMTP settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    DEFAULT_DB_PATH,
    DEFAULT_EMAIL_FOOTER_PATH,
    DEFAULT_IMAP_PORT,
    DEFAULT_SEND_LATER_END_HOUR,
    DEFAULT_SEND_LATER_START_HOUR,
    DEFAULT_SMTP_PORT,
    DEFAULT_USER_TIMEZONE,
    ENV_ASSISTANT_DB_PATH,
    ENV_EMAIL_FOOTER_PATH,
    ENV_EMAIL_FROM_ADDRESS,
    ENV_IMAP_PASSWORD,
    ENV_IMAP_PORT,
    ENV_IMAP_SERVER,
    ENV_IMAP_USE_SSL,
    ENV_IMAP_USERNAME,
    ENV_SEND_LATER_ENABLED,
    ENV_SEND_LATER_END_HOUR,
    ENV_SEND_LATER_START_HOUR,
    ENV_SMTP_PASSWORD,
    ENV_SMTP_PORT,
    ENV_SMTP_SERVER,
    ENV_SMTP_USERNAME,
    ENV_USER_TIMEZONE,
)


@dataclass(frozen=True)
class ImapSettings:
    """IMAP connection settings."""

    server: str
    username: str
    password: str
    port: int = DEFAULT_IMAP_PORT
    use_ssl: bool = True


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP connection settings."""

    server: str
    port: int = DEFAULT_SMTP_PORT
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class DatabaseSettings:
    """SQLite database settings."""

    db_path: str = DEFAULT_DB_PATH


@dataclass(frozen=True)
class EmailSettings:
    """Combined email settings."""

    imap: ImapSettings
    smtp: SmtpSettings
    from_address: str
    footer_html: str = ""
    send_later_enabled: bool = True
    send_later_start_hour: int = DEFAULT_SEND_LATER_START_HOUR
    send_later_end_hour: int = DEFAULT_SEND_LATER_END_HOUR
    timezone: str = DEFAULT_USER_TIMEZONE


def load_email_settings() -> EmailSettings | None:
    """Load email settings from environment variables.

    Returns None if IMAP_SERVER is not configured.
    """
    imap_server = os.environ.get(ENV_IMAP_SERVER, "")
    if not imap_server:
        return None

    imap_username = os.environ.get(ENV_IMAP_USERNAME, "")
    imap_password = os.environ.get(ENV_IMAP_PASSWORD, "")

    imap = ImapSettings(
        server=imap_server,
        username=imap_username,
        password=imap_password,
        port=int(os.environ.get(ENV_IMAP_PORT, str(DEFAULT_IMAP_PORT))),
        use_ssl=os.environ.get(ENV_IMAP_USE_SSL, "true").lower() == "true",
    )

    smtp_server = os.environ.get(ENV_SMTP_SERVER, "")
    if not smtp_server:
        smtp_server = imap_server.replace("imap", "smtp")

    smtp = SmtpSettings(
        server=smtp_server,
        port=int(os.environ.get(ENV_SMTP_PORT, str(DEFAULT_SMTP_PORT))),
        username=os.environ.get(ENV_SMTP_USERNAME, imap_username),
        password=os.environ.get(ENV_SMTP_PASSWORD, imap_password),
    )

    from_address = os.environ.get(ENV_EMAIL_FROM_ADDRESS, imap_username)

    footer_html = ""
    footer_path = Path(os.environ.get(ENV_EMAIL_FOOTER_PATH, DEFAULT_EMAIL_FOOTER_PATH))
    if footer_path.is_file():
        footer_html = footer_path.read_text(encoding="utf-8")

    send_later_enabled = os.environ.get(
        ENV_SEND_LATER_ENABLED, "true",
    ).lower() == "true"
    send_later_start = int(os.environ.get(
        ENV_SEND_LATER_START_HOUR, str(DEFAULT_SEND_LATER_START_HOUR),
    ))
    send_later_end = int(os.environ.get(
        ENV_SEND_LATER_END_HOUR, str(DEFAULT_SEND_LATER_END_HOUR),
    ))
    timezone = os.environ.get(ENV_USER_TIMEZONE, DEFAULT_USER_TIMEZONE)

    return EmailSettings(
        imap=imap,
        smtp=smtp,
        from_address=from_address,
        footer_html=footer_html,
        send_later_enabled=send_later_enabled,
        send_later_start_hour=send_later_start,
        send_later_end_hour=send_later_end,
        timezone=timezone,
    )


def load_database_settings() -> DatabaseSettings:
    """Load database settings from environment variables."""
    db_path = os.environ.get(ENV_ASSISTANT_DB_PATH, DEFAULT_DB_PATH)
    return DatabaseSettings(db_path=db_path)
