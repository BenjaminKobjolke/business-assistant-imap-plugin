"""Compose operations mixin for EmailService (reply, forward, send)."""

from __future__ import annotations

import contextlib
import html
import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .constants import MIME_TEXT_HTML, MIME_TEXT_PLAIN, SNIPPET_MAX_CHARS
from .draft_builder import (
    DraftEmailContent,
    assemble_forward_html,
    assemble_reply_html,
    make_forward_subject,
    make_reply_subject,
    save_draft_to_imap,
)
from .send_later import build_send_at_headers, build_send_later_headers

logger = logging.getLogger(__name__)


def _extract_reply_address(from_address: str) -> str:
    """Extract a clean email address from a From header value."""
    match = re.search(r"<([^>]+)>", from_address)
    if match:
        return match.group(1)
    return from_address.strip()


class ComposeMixin:
    """Compose/reply/forward methods — mixed into EmailService."""

    def _get_send_later_headers(
        self, send_at: str | None = None,
    ) -> dict[str, str] | None:
        """Build Send Later headers.

        If *send_at* is provided (ISO 8601 string), schedule for that exact
        time.  Otherwise fall back to automatic business-hours scheduling.
        """
        tz = ZoneInfo(self._settings.timezone)
        if send_at:
            dt = datetime.fromisoformat(send_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return build_send_at_headers(dt)
        if not self._settings.send_later_enabled:
            return None
        now = datetime.now(tz)
        return build_send_later_headers(
            now, self._settings.send_later_start_hour,
            self._settings.send_later_end_hour,
        )

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
        include_footer: bool = True,
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
        footer = self._settings.footer_html if include_footer else ""
        html_body = assemble_reply_html(content, footer_html=footer)
        return content, html_body

    def _build_forward(
        self, email_msg: object, additional_message: str,
        include_footer: bool = True,
    ) -> tuple[str, str, list]:
        """Build forward subject, HTML body, and attachments list."""
        original_html = email_msg.get_body(MIME_TEXT_HTML)
        if original_html:
            original_body = original_html
            is_html = True
        else:
            original_body = email_msg.get_body(MIME_TEXT_PLAIN) or ""
            is_html = False
        original_from = email_msg.from_address or ""
        original_to = email_msg.raw_message.get("To", "")
        original_date = email_msg.date or ""
        original_subject = email_msg.subject or ""

        footer = self._settings.footer_html if include_footer else ""
        html_body = assemble_forward_html(
            additional_message=additional_message,
            original_from=original_from,
            original_to=original_to,
            original_date=original_date,
            original_subject=original_subject,
            original_body=original_body,
            footer_html=footer,
            original_is_html=is_html,
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
        include_footer: bool = True,
        send_at: str | None = None,
    ) -> str:
        """Save a reply draft to an email."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=False,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            content, html_body = self._build_reply(
                email_msg, reply_body, greeting,
                include_footer=include_footer,
            )
            success = save_draft_to_imap(
                client=client,
                to_address=content.to_address,
                subject=content.subject,
                html_body=html_body,
                from_email=self._settings.from_address,
                custom_headers=self._get_send_later_headers(
                    send_at=send_at,
                ),
            )
            if success:
                if send_at:
                    return f"Draft reply saved and scheduled for {send_at}."
                return "Draft reply saved."
            return "Failed to save draft reply."
        finally:
            client.disconnect()

    def send_reply(
        self,
        email_id: str,
        reply_body: str,
        greeting: str = "",
        folder: str = "INBOX",
        include_footer: bool = True,
    ) -> str:
        """Send a reply to an email directly via SMTP."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=False,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            content, html_body = self._build_reply(
                email_msg, reply_body, greeting,
                include_footer=include_footer,
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
        finally:
            client.disconnect()

    def forward_email(
        self,
        email_id: str,
        to_addresses: list[str],
        additional_message: str = "",
        folder: str = "INBOX",
        include_footer: bool = True,
    ) -> str:
        """Forward an email preserving all attachments and inline images."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            subject, html_body, attachments = self._build_forward(
                email_msg, additional_message,
                include_footer=include_footer,
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
        finally:
            client.disconnect()

    def draft_forward(
        self,
        email_id: str,
        to_address: str,
        additional_message: str = "",
        folder: str = "INBOX",
        include_footer: bool = True,
        send_at: str | None = None,
    ) -> str:
        """Save a forward draft preserving attachments and inline images."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            subject, html_body, attachments = self._build_forward(
                email_msg, additional_message,
                include_footer=include_footer,
            )
            try:
                fwd_kwargs: dict = {
                    "to_addresses": [to_address],
                    "subject": subject,
                    "body": html_body,
                    "from_email": self._settings.from_address,
                    "content_type": MIME_TEXT_HTML,
                    "attachments": attachments,
                }
                sl_headers = self._get_send_later_headers(
                    send_at=send_at,
                )
                if sl_headers:
                    fwd_kwargs["custom_headers"] = sl_headers
                success = client.save_draft(**fwd_kwargs)
                if success:
                    if send_at:
                        return f"Forward draft saved and scheduled for {send_at}."
                    return "Forward draft saved."
                return "Failed to save forward draft."
            except Exception as e:
                logger.error(
                    "Error saving forward draft: %s", e
                )
                return "Failed to save forward draft."
        finally:
            client.disconnect()

    def compose_email(
        self,
        to_addresses: list[str],
        subject: str,
        body: str,
        bcc_addresses: list[str] | None = None,
        content_type: str = "text/html",
        include_footer: bool = True,
    ) -> str:
        """Send a new composed email via SMTP with optional BCC."""
        if include_footer and content_type == MIME_TEXT_HTML and self._settings.footer_html:
            body = body + f'<div style="margin-top: 20px;">{self._settings.footer_html}</div>'
        client = self._create_client()
        try:
            success = client.send_email(
                to_addresses=to_addresses,
                subject=subject,
                body=body,
                content_type=content_type,
                from_email=self._settings.from_address,
                bcc_addresses=bcc_addresses,
                **self._smtp_kwargs(),
            )
            if success:
                self._save_to_sent(client, to_addresses, subject, body)
                recipients = ", ".join(to_addresses)
                return f"Email sent to {recipients}."
            return "Failed to send email."
        finally:
            client.disconnect()

    def draft_compose(
        self,
        to_addresses: list[str],
        subject: str,
        body: str,
        bcc_addresses: list[str] | None = None,
        content_type: str = "text/html",
        include_footer: bool = True,
        send_at: str | None = None,
    ) -> str:
        """Save a new composed email as draft with optional BCC."""
        if include_footer and content_type == MIME_TEXT_HTML and self._settings.footer_html:
            body = body + f'<div style="margin-top: 20px;">{self._settings.footer_html}</div>'
        client = self._create_client()
        try:
            kwargs: dict = {
                "to_addresses": to_addresses,
                "subject": subject,
                "body": body,
                "from_email": self._settings.from_address,
                "content_type": content_type,
            }
            if bcc_addresses:
                kwargs["bcc_addresses"] = bcc_addresses
            sl_headers = self._get_send_later_headers(send_at=send_at)
            if sl_headers:
                kwargs["custom_headers"] = sl_headers
            success = client.save_draft(**kwargs)
            if success:
                if send_at:
                    return f"Compose draft saved and scheduled for {send_at}."
                return "Compose draft saved."
            return "Failed to save compose draft."
        finally:
            client.disconnect()

    def edit_draft(
        self,
        email_id: str,
        subject: str = "",
        body: str = "",
        to_addresses: list[str] | None = None,
    ) -> str:
        """Edit a draft by replacing it with a new one.

        Only non-empty parameters override the original values.
        Internally: fetches original, trashes it, creates new draft.
        """
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder="Drafts",
                include_attachments=False,
            )
            if result is None:
                return "Draft not found in Drafts folder."
            msg_id, email_msg = result

            orig_to = email_msg.raw_message.get("To", "")
            orig_subject = email_msg.subject or ""
            orig_body = (
                email_msg.get_body(MIME_TEXT_HTML)
                or email_msg.get_body(MIME_TEXT_PLAIN)
                or ""
            )
            orig_bcc = email_msg.raw_message.get("Bcc", "")

            new_subject = subject if subject else orig_subject
            new_body = body if body else orig_body
            new_to = (
                to_addresses if to_addresses
                else [a.strip() for a in orig_to.split(",") if a.strip()]
            )
            bcc_list = (
                [a.strip() for a in orig_bcc.split(",") if a.strip()]
                or None
            )
        finally:
            client.disconnect()

        # Trash old draft
        self.move_email(email_id, "Trash", source_folder="Drafts")

        # Create new draft
        return self.draft_compose(
            to_addresses=new_to,
            subject=new_subject,
            body=new_body,
            bcc_addresses=bcc_list,
            include_footer=False,
        )

    def search_sent_to(self, email_address: str, limit: int = 3) -> str:
        """Search the Sent folder for recent emails to a specific address.

        Uses IMAP server-side TO search for performance.
        Returns the start and end of each email body so the agent can
        detect writing style: salutation, tone, language, and sign-off patterns.
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

                clean = " ".join(body.split()) if body else ""
                body_start = clean[:SNIPPET_MAX_CHARS]
                body_end = (
                    clean[-SNIPPET_MAX_CHARS:]
                    if len(clean) > SNIPPET_MAX_CHARS * 2
                    else ""
                )
                items.append({
                    "_id": str(msg_id),
                    "subject": email_msg.subject or "(no subject)",
                    "date": email_msg.date or "",
                    "body_start": body_start,
                    "body_end": body_end,
                })

            if not items:
                return f"No sent emails to {email_address} found."

            return json.dumps({"sent_emails": items})
        finally:
            client.disconnect()
