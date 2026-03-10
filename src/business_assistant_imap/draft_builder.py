"""Draft email composition — build and save reply drafts.

Ported from imap-ai-assistant draft_email_builder.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .constants import MIME_TEXT_HTML, PREFIX_FORWARD, PREFIX_REPLY

logger = logging.getLogger(__name__)


@dataclass
class DraftEmailContent:
    """All data needed to assemble and save a draft reply."""

    to_address: str
    subject: str
    greeting: str
    body_text: str
    original_from: str
    original_subject: str
    original_body: str


def make_reply_subject(original_subject: str) -> str:
    """Ensure subject starts with 'Re: '."""
    if original_subject.lower().startswith("re: "):
        return original_subject
    return f"{PREFIX_REPLY}{original_subject}"


def make_forward_subject(original_subject: str) -> str:
    """Ensure subject starts with 'Fwd: '."""
    if original_subject.lower().startswith("fwd: "):
        return original_subject
    return f"{PREFIX_FORWARD}{original_subject}"


def assemble_forward_html(
    additional_message: str,
    original_from: str,
    original_to: str,
    original_date: str,
    original_subject: str,
    original_body: str,
    footer_html: str = "",
) -> str:
    """Build HTML body for a forwarded email."""
    html_additional = additional_message.replace("\n", "<br>") if additional_message else ""
    html_original = original_body.replace("\n", "<br>")

    additional_block = ""
    if html_additional:
        additional_block = f"""
    <div style="margin-bottom: 20px;">
        {html_additional}
    </div>"""

    footer_block = ""
    if footer_html:
        footer_block = f"""
    <div style="margin-top: 20px;">
        {footer_html}
    </div>"""

    return f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">
    {additional_block}
    {footer_block}

    <hr style="margin: 20px 0; border: none; border-top: 1px solid #ccc;">

    <div style="color: #666; font-size: 12px; background-color: #f9f9f9; \
padding: 10px; border-left: 3px solid #ddd;">
        <strong>---------- Forwarded message ----------</strong><br>
        <strong>From:</strong> {original_from}<br>
        <strong>Date:</strong> {original_date}<br>
        <strong>Subject:</strong> {original_subject}<br>
        <strong>To:</strong> {original_to}<br><br>
        <div style="margin-top: 10px;">
            {html_original}
        </div>
    </div>
</div>
"""


def assemble_reply_html(content: DraftEmailContent, footer_html: str = "") -> str:
    """Build HTML body from greeting + body + quoted original."""
    html_body_text = content.body_text.replace("\n", "<br>")
    html_original = content.original_body.replace("\n", "<br>")

    greeting_block = ""
    if content.greeting:
        greeting_block = f'<div style="margin-bottom: 10px;">{content.greeting},</div>'

    footer_block = ""
    if footer_html:
        footer_block = f"""
    <div style="margin-top: 20px;">
        {footer_html}
    </div>"""

    return f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;">
    {greeting_block}
    <div style="margin-bottom: 20px;">
        {html_body_text}
    </div>
    {footer_block}

    <hr style="margin: 20px 0; border: none; border-top: 1px solid #ccc;">

    <div style="color: #666; font-size: 12px; background-color: #f9f9f9; \
padding: 10px; border-left: 3px solid #ddd;">
        <strong>-----Original Message-----</strong><br>
        <strong>From:</strong> {content.original_from}<br>
        <strong>Subject:</strong> {content.original_subject}<br><br>
        <div style="margin-top: 10px;">
            {html_original}
        </div>
    </div>
</div>
"""


def save_draft_to_imap(
    client: object,
    to_address: str,
    subject: str,
    html_body: str,
    from_email: str,
    draft_folder: str = "Drafts",
) -> bool:
    """Save the assembled email as a draft via IMAP client.

    Args:
        client: ImapClient instance (must be connected).
        to_address: Recipient email address.
        subject: Email subject.
        html_body: HTML body content.
        from_email: Sender email address.
        draft_folder: IMAP folder name for drafts.
    """
    try:
        success = client.save_draft(
            to_addresses=[to_address],
            subject=subject,
            body=html_body,
            from_email=from_email,
            draft_folder=draft_folder,
            content_type=MIME_TEXT_HTML,
        )
        if success:
            logger.info("Draft reply saved for %s: %s", to_address, subject)
        else:
            logger.error("Failed to save draft for %s", to_address)
        return bool(success)
    except Exception as e:
        logger.error("Error saving draft: %s", e)
        return False
