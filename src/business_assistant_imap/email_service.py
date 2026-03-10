"""EmailService — wraps ImapClient for all email operations."""

from __future__ import annotations

import contextlib
import html
import json
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

            emails = []
            for msg_id, email_msg in messages:
                emails.append({
                    "_id": str(msg_id),
                    "from": email_msg.from_address or "(unknown)",
                    "subject": email_msg.subject or "(no subject)",
                    "date": email_msg.date or "",
                })
            return json.dumps({"emails": emails})
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
                    att_names = (
                        [a.filename for a in email_msg.attachments]
                        if email_msg.attachments
                        else []
                    )
                    return json.dumps({
                        "_id": str(msg_id),
                        "from": email_msg.from_address or "",
                        "subject": email_msg.subject or "",
                        "date": email_msg.date or "",
                        "body": body,
                        "attachments": att_names,
                    })
            return "Email not found."
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

            results = []
            for msg_id, email_msg in matches:
                results.append({
                    "_id": str(msg_id),
                    "from": email_msg.from_address or "",
                    "subject": email_msg.subject or "",
                    "date": email_msg.date or "",
                })
            return json.dumps({"results": results})
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
                return f"Email moved to '{destination_folder}'."
            return "Failed to move email."
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
                        return "No meeting data found in this email."

                    ics_data = extract_ics_data(email_msg)
                    ics_text = ics_data.decode("utf-8", errors="replace") if ics_data else None
                    parsed = parse_vevent(ics_text) if ics_text else None

                    info: dict[str, str | None] = {
                        "_id": str(msg_id),
                        "start": dtstart.strftime("%Y-%m-%d %H:%M %Z"),
                        "end": dtend.strftime("%Y-%m-%d %H:%M %Z") if dtend else None,
                        "organizer": None,
                        "location": None,
                    }
                    if parsed:
                        info["organizer"] = parsed.get("organizer")
                        info["location"] = parsed.get("location")
                    return json.dumps(
                        {k: v for k, v in info.items() if v is not None}
                    )
            return "Email not found."
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
            items = []
            for msg_id, email_msg, dtstart, dtend in appointments:
                items.append({
                    "_id": str(msg_id),
                    "start": dtstart.strftime("%Y-%m-%d %H:%M"),
                    "end": dtend.strftime("%H:%M") if dtend else None,
                    "subject": email_msg.subject or "(no subject)",
                })
            return json.dumps({"appointments": items})
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
                        return "No meeting links found in this email."
                    return json.dumps({
                        "_id": str(msg_id),
                        "links": [{"type": lnk["type"], "url": lnk["url"]} for lnk in links],
                    })
            return "Email not found."
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
                        return "This email does not contain a calendar invite."
                    info: dict[str, str | bool | None] = {
                        "_id": str(msg_id),
                        "subject": invite.summary or invite.subject,
                    }
                    if invite.dtstart:
                        info["when"] = invite.dtstart.strftime("%Y-%m-%d %H:%M")
                        if invite.dtend:
                            info["until"] = invite.dtend.strftime("%H:%M")
                    if invite.organizer:
                        info["organizer"] = invite.organizer
                    if invite.location:
                        info["location"] = invite.location
                    if invite.is_cancellation:
                        info["cancelled"] = True
                    return json.dumps(info)
            return "Email not found."
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
                        return "This email does not contain a calendar invite."

                    success = send_rsvp(
                        smtp_settings=self._settings.smtp,
                        invite=invite,
                        user_email=self._settings.from_address,
                        status=status.upper(),
                    )
                    if success:
                        return f"RSVP ({status}) sent to {invite.organizer_email}."
                    return "Failed to send RSVP."
            return "Email not found."
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
                        return "Draft reply saved."
                    return "Failed to save draft reply."
            return "Email not found."
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
                        return "Reply sent."
                    return "Failed to send reply."
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
                        raw_html = email_msg.get_body("text/html") or ""
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


def _extract_reply_address(from_address: str) -> str:
    """Extract a clean email address from a From header value."""
    match = re.search(r"<([^>]+)>", from_address)
    if match:
        return match.group(1)
    return from_address.strip()
