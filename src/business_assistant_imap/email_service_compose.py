"""Compose operations mixin for EmailService (reply, forward, send)."""

from __future__ import annotations

import contextlib
import html
import json
import logging
import re

from .constants import MIME_TEXT_HTML, MIME_TEXT_PLAIN
from .draft_builder import (
    DraftEmailContent,
    assemble_forward_html,
    assemble_reply_html,
    make_forward_subject,
    make_reply_subject,
    save_draft_to_imap,
)

logger = logging.getLogger(__name__)


def _extract_reply_address(from_address: str) -> str:
    """Extract a clean email address from a From header value."""
    match = re.search(r"<([^>]+)>", from_address)
    if match:
        return match.group(1)
    return from_address.strip()


class ComposeMixin:
    """Compose/reply/forward methods — mixed into EmailService."""

    def _smtp_kwargs(self) -> dict:
        """Return SMTP connection kwargs from settings."""
        return {
            "smtp_server": self._settings.smtp.server,
            "smtp_port": self._settings.smtp.port,
            "smtp_username": self._settings.smtp.username,
            "smtp_password": self._settings.smtp.password,
        }

    def _build_reply(
        self, email_msg: object, reply_body: str, greeting: str,
    ) -> tuple[DraftEmailContent, str]:
        """Build reply content and HTML body from an email message."""
        original_body = email_msg.get_body(MIME_TEXT_PLAIN) or ""
        content = DraftEmailContent(
            to_address=_extract_reply_address(email_msg.from_address),
            subject=make_reply_subject(email_msg.subject or ""),
            greeting=greeting,
            body_text=reply_body,
            original_from=email_msg.from_address or "",
            original_subject=email_msg.subject or "",
            original_body=original_body,
        )
        html_body = assemble_reply_html(
            content, footer_html=self._settings.footer_html
        )
        return content, html_body

    def _build_forward(
        self, email_msg: object, additional_message: str,
    ) -> tuple[str, str, list]:
        """Build forward subject, HTML body, and attachments list."""
        original_body = email_msg.get_body(MIME_TEXT_PLAIN) or ""
        original_from = email_msg.from_address or ""
        original_to = email_msg.raw_message.get("To", "")
        original_date = email_msg.date or ""
        original_subject = email_msg.subject or ""

        html_body = assemble_forward_html(
            additional_message=additional_message,
            original_from=original_from,
            original_to=original_to,
            original_date=original_date,
            original_subject=original_subject,
            original_body=original_body,
            footer_html=self._settings.footer_html,
        )
        subject = make_forward_subject(original_subject)
        attachments = email_msg.attachments or []
        return subject, html_body, attachments

    def _save_to_sent(
        self,
        client: object,
        to_addresses: list[str],
        subject: str,
        html_body: str,
        attachments: list | None = None,
    ) -> None:
        """Append a copy of the sent message to the Sent folder."""
        try:
            kwargs: dict = {
                "to_addresses": to_addresses,
                "subject": subject,
                "body": html_body,
                "from_email": self._settings.from_address,
                "content_type": MIME_TEXT_HTML,
                "draft_folder": "Sent",
                "mark_as_unread": False,
            }
            if attachments:
                kwargs["attachments"] = attachments
            client.save_draft(**kwargs)
        except Exception:
            logger.warning(
                "Failed to save sent copy for: %s", subject
            )

    def draft_reply(
        self,
        email_id: str,
        reply_body: str,
        greeting: str = "",
        folder: str = "INBOX",
    ) -> str:
        """Save a reply draft to an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    content, html_body = self._build_reply(
                        email_msg, reply_body, greeting
                    )
                    success = save_draft_to_imap(
                        client=client,
                        to_address=content.to_address,
                        subject=content.subject,
                        html_body=html_body,
                        from_email=self._settings.from_address,
                    )
                    if success:
                        return "Draft reply saved."
                    return "Failed to save draft reply."
            return "Email not found."
        finally:
            client.disconnect()

    def send_reply(
        self,
        email_id: str,
        reply_body: str,
        greeting: str = "",
        folder: str = "INBOX",
    ) -> str:
        """Send a reply to an email directly via SMTP."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    content, html_body = self._build_reply(
                        email_msg, reply_body, greeting
                    )
                    success = client.send_email(
                        to_addresses=[content.to_address],
                        subject=content.subject,
                        body=html_body,
                        content_type="text/html",
                        from_email=self._settings.from_address,
                        **self._smtp_kwargs(),
                    )
                    if success:
                        self._save_to_sent(
                            client,
                            [content.to_address],
                            content.subject,
                            html_body,
                        )
                        return "Reply sent."
                    return "Failed to send reply."
            return "Email not found."
        finally:
            client.disconnect()

    def forward_email(
        self,
        email_id: str,
        to_addresses: list[str],
        additional_message: str = "",
        folder: str = "INBOX",
    ) -> str:
        """Forward an email preserving all attachments and inline images."""
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=True,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) == str(email_id):
                    subject, html_body, attachments = self._build_forward(
                        email_msg, additional_message
                    )
                    success = client.send_email(
                        to_addresses=to_addresses,
                        subject=subject,
                        body=html_body,
                        content_type="text/html",
                        from_email=self._settings.from_address,
                        attachments=attachments,
                        **self._smtp_kwargs(),
                    )
                    if success:
                        self._save_to_sent(
                            client,
                            to_addresses,
                            subject,
                            html_body,
                            attachments,
                        )
                        recipients = ", ".join(to_addresses)
                        return f"Email forwarded to {recipients}."
                    return "Failed to forward email."
            return "Email not found."
        finally:
            client.disconnect()

    def draft_forward(
        self,
        email_id: str,
        to_address: str,
        additional_message: str = "",
        folder: str = "INBOX",
    ) -> str:
        """Save a forward draft preserving attachments and inline images."""
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=True,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) == str(email_id):
                    subject, html_body, attachments = self._build_forward(
                        email_msg, additional_message
                    )
                    try:
                        success = client.save_draft(
                            to_addresses=[to_address],
                            subject=subject,
                            body=html_body,
                            from_email=self._settings.from_address,
                            content_type=MIME_TEXT_HTML,
                            attachments=attachments,
                        )
                        if success:
                            return "Forward draft saved."
                        return "Failed to save forward draft."
                    except Exception as e:
                        logger.error(
                            "Error saving forward draft: %s", e
                        )
                        return "Failed to save forward draft."
            return "Email not found."
        finally:
            client.disconnect()

    def search_sent_to(self, email_address: str, limit: int = 3) -> str:
        """Search the Sent folder for recent emails to a specific address.

        Uses IMAP server-side TO search for performance.
        Returns the first ~500 chars of each email body so the agent can
        detect salutation patterns.
        """
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["TO", email_address],
                folder="Sent",
                limit=limit,
                include_attachments=False,
            )
            if not messages:
                return f"No sent emails to {email_address} found."

            items: list[dict[str, str]] = []
            for msg_id, email_msg in messages:
                body = ""
                with contextlib.suppress(Exception):
                    body = email_msg.get_body(MIME_TEXT_PLAIN) or ""
                if not body:
                    with contextlib.suppress(Exception):
                        raw_html = (
                            email_msg.get_body("text/html") or ""
                        )
                        body = re.sub(r"<[^>]+>", "", raw_html)
                        body = html.unescape(body)

                clean = " ".join(body.split())[:500] if body else ""
                items.append({
                    "_id": str(msg_id),
                    "subject": email_msg.subject or "(no subject)",
                    "date": email_msg.date or "",
                    "body_snippet": clean,
                })

            if not items:
                return f"No sent emails to {email_address} found."

            return json.dumps({"sent_emails": items})
        finally:
            client.disconnect()
