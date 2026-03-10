"""EmailService — wraps ImapClient for all email operations."""

from __future__ import annotations

import contextlib
import html
import logging
import re
from datetime import date

from imap_client_lib.account import Account
from imap_client_lib.client import ImapClient

from .config import EmailSettings
from .constants import MIME_TEXT_PLAIN
from .draft_builder import (
    DraftEmailContent,
    assemble_reply_html,
    make_reply_subject,
    save_draft_to_imap,
)
from .invite_handler import detect_invite, send_rsvp
from .meeting_parser import (
    extract_ics_data,
    extract_meeting_links,
    extract_meeting_times,
    parse_vevent,
)

logger = logging.getLogger(__name__)


class EmailService:
    """High-level email operations wrapping ImapClient.

    Each operation connects and disconnects per call (try/finally pattern).
    """

    def __init__(self, email_settings: EmailSettings) -> None:
        self._settings = email_settings
        self._account = Account(
            name="main",
            server=email_settings.imap.server,
            username=email_settings.imap.username,
            password=email_settings.imap.password,
            port=email_settings.imap.port,
            use_ssl=email_settings.imap.use_ssl,
        )

    def _create_client(self) -> ImapClient:
        """Create and connect a new ImapClient."""
        client = ImapClient(self._account)
        if not client.connect():
            raise ConnectionError(f"Failed to connect to {self._account.server}")
        return client

    def list_inbox(self, limit: int = 20) -> str:
        """List recent emails from the inbox."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX", limit=limit)
            if not messages:
                return "No emails found in inbox."

            lines = [f"Inbox ({len(messages)} emails):"]
            for msg_id, email_msg in messages:
                from_addr = email_msg.from_address or "(unknown)"
                subject = email_msg.subject or "(no subject)"
                date_str = email_msg.date or ""
                lines.append(f"  [{msg_id}] From: {from_addr} | Subject: {subject} | {date_str}")
            return "\n".join(lines)
        finally:
            client.disconnect()

    def show_email(self, email_id: str, folder: str = "INBOX") -> str:
        """Show full details of a specific email."""
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=True,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) == str(email_id):
                    body = email_msg.get_body(MIME_TEXT_PLAIN) or "(no text body)"
                    attachments = ""
                    if email_msg.attachments:
                        att_names = [a.filename for a in email_msg.attachments]
                        attachments = f"\nAttachments: {', '.join(att_names)}"
                    return (
                        f"From: {email_msg.from_address}\n"
                        f"Subject: {email_msg.subject}\n"
                        f"Date: {email_msg.date}\n"
                        f"{attachments}\n\n"
                        f"{body}"
                    )
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def search_emails(self, query: str, folder: str = "INBOX", limit: int = 20) -> str:
        """Search emails by query string (searches From, Subject, Body)."""
        client = self._create_client()
        try:
            criteria = ["ALL"]
            messages = client.get_messages(
                search_criteria=criteria,
                folder=folder,
                limit=limit,
                include_attachments=False,
            )
            if not messages:
                return f"No emails found in {folder}."

            query_lower = query.lower()
            matches = []
            for msg_id, email_msg in messages:
                from_addr = (email_msg.from_address or "").lower()
                subject = (email_msg.subject or "").lower()
                body = ""
                with contextlib.suppress(Exception):
                    body = (email_msg.get_body(MIME_TEXT_PLAIN) or "").lower()

                if query_lower in from_addr or query_lower in subject or query_lower in body:
                    matches.append((msg_id, email_msg))

            if not matches:
                return f"No emails matching '{query}' found."

            lines = [f"Search results for '{query}' ({len(matches)} found):"]
            for msg_id, email_msg in matches:
                lines.append(
                    f"  [{msg_id}] From: {email_msg.from_address} | "
                    f"Subject: {email_msg.subject} | {email_msg.date}"
                )
            return "\n".join(lines)
        finally:
            client.disconnect()

    def list_folders(self) -> str:
        """List all mailbox folders."""
        client = self._create_client()
        try:
            folders = client.list_folders()
            if not folders:
                return "No folders found."
            lines = ["Mailbox folders:"]
            for folder in sorted(folders):
                lines.append(f"  - {folder}")
            return "\n".join(lines)
        finally:
            client.disconnect()

    def move_email(self, email_id: str, destination_folder: str) -> str:
        """Move an email to a different folder."""
        client = self._create_client()
        try:
            client.client.select_folder("INBOX")
            success = client.move_to_folder(email_id, destination_folder)
            if success:
                return f"Email {email_id} moved to '{destination_folder}'."
            return f"Failed to move email {email_id}."
        finally:
            client.disconnect()

    def trash_email(self, email_id: str) -> str:
        """Move an email to the Trash folder."""
        return self.move_email(email_id, "Trash")

    def get_unread_count(self) -> str:
        """Get the number of unread emails in the inbox."""
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["UNSEEN"],
                folder="INBOX",
                include_attachments=False,
            )
            count = len(messages)
            return f"You have {count} unread email(s)."
        finally:
            client.disconnect()

    def get_meeting_info(self, email_id: str) -> str:
        """Get meeting/calendar details from an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    dtstart, dtend = extract_meeting_times(email_msg)
                    if dtstart is None:
                        return f"No meeting data found in email {email_id}."

                    ics_data = extract_ics_data(email_msg)
                    ics_text = ics_data.decode("utf-8", errors="replace") if ics_data else None
                    parsed = parse_vevent(ics_text) if ics_text else None

                    lines = [f"Meeting in email {email_id}:"]
                    lines.append(f"  Start: {dtstart.strftime('%Y-%m-%d %H:%M %Z')}")
                    if dtend:
                        lines.append(f"  End:   {dtend.strftime('%Y-%m-%d %H:%M %Z')}")
                    if parsed:
                        if parsed.get("organizer"):
                            lines.append(f"  Organizer: {parsed['organizer']}")
                        if parsed.get("location"):
                            lines.append(f"  Location: {parsed['location']}")
                    return "\n".join(lines)
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def get_appointments(self, folder: str = "INBOX") -> str:
        """List upcoming appointments from emails with ICS data."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
            if not messages:
                return f"No emails found in {folder}."

            today = date.today()
            appointments = []
            for msg_id, email_msg in messages:
                dtstart, dtend = extract_meeting_times(email_msg)
                if dtstart and dtstart.date() >= today:
                    appointments.append((msg_id, email_msg, dtstart, dtend))

            if not appointments:
                return "No upcoming appointments found."

            appointments.sort(key=lambda x: x[2])
            lines = [f"Upcoming appointments ({len(appointments)}):"]
            for msg_id, email_msg, dtstart, dtend in appointments:
                start_str = dtstart.strftime("%Y-%m-%d %H:%M")
                end_str = dtend.strftime("%H:%M") if dtend else "??:??"
                subject = email_msg.subject or "(no subject)"
                lines.append(f"  [{msg_id}] {start_str} - {end_str} | {subject}")
            return "\n".join(lines)
        finally:
            client.disconnect()

    def get_meeting_links(self, email_id: str) -> str:
        """Extract meeting links (Teams, Zoom, Meet) from an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    ics_data = extract_ics_data(email_msg)
                    ics_text = ics_data.decode("utf-8", errors="replace") if ics_data else None
                    links = extract_meeting_links(email_msg, ics_text)
                    if not links:
                        return f"No meeting links found in email {email_id}."
                    lines = [f"Meeting links in email {email_id}:"]
                    for link in links:
                        lines.append(f"  {link['type']}: {link['url']}")
                    return "\n".join(lines)
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def detect_invite_in_email(self, email_id: str) -> str:
        """Check if an email contains a calendar invite."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    invite = detect_invite(str(msg_id), email_msg)
                    if invite is None:
                        return f"Email {email_id} does not contain a calendar invite."
                    lines = [f"Calendar invite found in email {email_id}:"]
                    lines.append(f"  Subject: {invite.summary or invite.subject}")
                    if invite.dtstart:
                        lines.append(f"  When: {invite.dtstart.strftime('%Y-%m-%d %H:%M')}")
                        if invite.dtend:
                            lines.append(f"  Until: {invite.dtend.strftime('%H:%M')}")
                    if invite.organizer:
                        lines.append(f"  Organizer: {invite.organizer}")
                    if invite.location:
                        lines.append(f"  Location: {invite.location}")
                    if invite.is_cancellation:
                        lines.append("  Status: CANCELLED")
                    return "\n".join(lines)
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def send_rsvp_for_email(self, email_id: str, status: str = "ACCEPTED") -> str:
        """Accept or decline a meeting invite by sending an RSVP."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
                    invite = detect_invite(str(msg_id), email_msg)
                    if invite is None:
                        return f"Email {email_id} does not contain a calendar invite."

                    success = send_rsvp(
                        smtp_settings=self._settings.smtp,
                        invite=invite,
                        user_email=self._settings.from_address,
                        status=status.upper(),
                    )
                    if success:
                        return f"RSVP ({status}) sent to {invite.organizer_email}."
                    return "Failed to send RSVP."
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def draft_reply(self, email_id: str, reply_body: str, greeting: str = "") -> str:
        """Save a reply draft to an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
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
                    html_body = assemble_reply_html(content)
                    success = save_draft_to_imap(
                        client=client,
                        to_address=content.to_address,
                        subject=content.subject,
                        html_body=html_body,
                        from_email=self._settings.from_address,
                    )
                    if success:
                        return f"Draft reply saved for email {email_id}."
                    return "Failed to save draft reply."
            return f"Email with ID {email_id} not found."
        finally:
            client.disconnect()

    def send_reply(self, email_id: str, reply_body: str, greeting: str = "") -> str:
        """Send a reply to an email directly via SMTP."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder="INBOX")
            for msg_id, email_msg in (messages or []):
                if str(msg_id) == str(email_id):
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
                    html_body = assemble_reply_html(content)

                    success = client.send_email(
                        to_addresses=[content.to_address],
                        subject=content.subject,
                        body=html_body,
                        content_type="text/html",
                        from_email=self._settings.from_address,
                        smtp_server=self._settings.smtp.server,
                        smtp_port=self._settings.smtp.port,
                        smtp_username=self._settings.smtp.username,
                        smtp_password=self._settings.smtp.password,
                    )
                    if success:
                        return f"Reply sent for email {email_id}."
                    return "Failed to send reply."
            return f"Email with ID {email_id} not found."
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

            entries: list[tuple[str, str, str, str]] = []
            for msg_id, email_msg in messages:
                body = ""
                with contextlib.suppress(Exception):
                    body = email_msg.get_body(MIME_TEXT_PLAIN) or ""
                if not body:
                    with contextlib.suppress(Exception):
                        raw_html = email_msg.get_body("text/html") or ""
                        body = re.sub(r"<[^>]+>", "", raw_html)
                        body = html.unescape(body)

                clean = " ".join(body.split())[:500] if body else ""
                subject = email_msg.subject or "(no subject)"
                date_str = email_msg.date or ""
                entries.append((str(msg_id), subject, date_str, clean))

            if not entries:
                return f"No sent emails to {email_address} found."

            lines = [f"Recent sent emails to {email_address} ({len(entries)} found):"]
            for i, (msg_id, subject, date_str, body_text) in enumerate(entries, 1):
                lines.append(
                    f"\n--- Email {i} ---\n"
                    f"[{msg_id}] Subject: {subject} | Date: {date_str}\n"
                    f"{body_text}"
                )
            return "\n".join(lines)
        finally:
            client.disconnect()


def _extract_reply_address(from_address: str) -> str:
    """Extract a clean email address from a From header value."""
    match = re.search(r"<([^>]+)>", from_address)
    if match:
        return match.group(1)
    return from_address.strip()
