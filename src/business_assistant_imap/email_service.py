"""EmailService — wraps ImapClient for all email operations."""

from __future__ import annotations

import contextlib
import difflib
import html
import json
import logging
import re
from datetime import date

from imap_client_lib.account import Account
from imap_client_lib.client import ImapClient

from .config import EmailSettings
from .constants import (
    FILTER_ACTION_MOVE,
    FILTER_ACTION_TRASH,
    FILTER_INVALID_ACTION,
    FILTER_INVALID_REGEX,
    FILTER_MOVE_NO_DESTINATION,
    FILTER_NO_PATTERN,
    FILTER_VALID_ACTIONS,
    FOLDER_NOT_FOUND,
    FOLDER_NOT_FOUND_NO_SUGGESTIONS,
    MAX_FOLDER_SUGGESTIONS,
    MIME_TEXT_HTML,
    MIME_TEXT_PLAIN,
)
from .draft_builder import (
    DraftEmailContent,
    assemble_forward_html,
    assemble_reply_html,
    make_forward_subject,
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

    def _resolve_folder(
        self, client: ImapClient, folder: str
    ) -> tuple[str, str | None]:
        """Validate *folder* against server folder list.

        Returns ``(resolved_folder, None)`` on success, or
        ``(folder, error_message)`` when the folder is not found.
        If the server returns no folders, validation is skipped.
        """
        all_folders: list[str] = client.list_folders() or []
        if not all_folders:
            return folder, None

        # 1. Exact match
        if folder in all_folders:
            return folder, None

        # 2. Case-insensitive exact match
        folder_lower = folder.lower()
        for srv in all_folders:
            if srv.lower() == folder_lower:
                return srv, None

        # 3. Collect suggestions: substring then fuzzy
        suggestions: list[str] = []

        # Substring (case-insensitive)
        for srv in all_folders:
            if folder_lower in srv.lower():
                suggestions.append(srv)

        # Fuzzy on leaf segment
        if len(suggestions) < MAX_FOLDER_SUGGESTIONS:
            leaves = {s.rsplit("/", 1)[-1]: s for s in all_folders}
            fuzzy = difflib.get_close_matches(
                folder, list(leaves.keys()), n=MAX_FOLDER_SUGGESTIONS, cutoff=0.4
            )
            for leaf in fuzzy:
                full = leaves[leaf]
                if full not in suggestions:
                    suggestions.append(full)

        suggestions = suggestions[:MAX_FOLDER_SUGGESTIONS]

        if suggestions:
            lines = "\n".join(f"  - {s}" for s in suggestions)
            return folder, FOLDER_NOT_FOUND.format(folder=folder, suggestions=lines)
        return folder, FOLDER_NOT_FOUND_NO_SUGGESTIONS.format(folder=folder)

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

    def list_messages(self, folder: str = "INBOX", limit: int = 20) -> str:
        """List recent emails from a specific folder."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error

            messages = client.get_all_messages(folder=folder, limit=limit)
            if not messages:
                return f"No emails found in {folder}."

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
                    to_addr = email_msg.raw_message.get("To", "")
                    cc_addr = email_msg.raw_message.get("Cc", "")

                    att_info: list[dict] = []
                    for a in email_msg.attachments or []:
                        entry: dict = {
                            "filename": a.filename,
                            "content_type": a.content_type,
                            "size": len(a.data) if a.data else 0,
                        }
                        if a.content_id:
                            entry["content_id"] = a.content_id
                        if a.is_inline:
                            entry["is_inline"] = True
                        att_info.append(entry)

                    return json.dumps({
                        "_id": str(msg_id),
                        "from": email_msg.from_address or "",
                        "to": to_addr,
                        "cc": cc_addr,
                        "subject": email_msg.subject or "",
                        "date": email_msg.date or "",
                        "body": body,
                        "attachments": att_info,
                    })
            return "Email not found."
        finally:
            client.disconnect()

    def get_attachment_url(
        self,
        email_id: str,
        filename: str,
        folder: str = "INBOX",
        ftp_service: object | None = None,
    ) -> str:
        """Upload a specific attachment via FTP and return a shareable URL."""
        if not ftp_service:
            return "FTP upload not configured."

        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=True,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) == str(email_id):
                    for a in email_msg.attachments or []:
                        if a.filename == filename:
                            try:
                                url = ftp_service.upload(a.data, a.filename)
                            except Exception:
                                logger.warning(
                                    "FTP upload failed for %s", a.filename
                                )
                                return f"FTP upload failed for '{filename}'."
                            return json.dumps({
                                "filename": a.filename,
                                "url": url,
                                "content_type": a.content_type,
                            })
                    return f"Attachment '{filename}' not found in email."
            return "Email not found."
        finally:
            client.disconnect()

    def filter_emails(
        self,
        subject_pattern: str = "",
        from_pattern: str = "",
        action: str = "trash",
        destination: str = "",
        folder: str = "INBOX",
        limit: int = 50,
        dry_run: bool = True,
    ) -> str:
        """Filter emails by subject/from regex patterns.

        dry_run=True previews matches without acting.
        dry_run=False applies the action (trash or move) to matches.
        """
        # Validate inputs before connecting
        if not subject_pattern and not from_pattern:
            return FILTER_NO_PATTERN
        if action not in FILTER_VALID_ACTIONS:
            return FILTER_INVALID_ACTION.format(action=action)
        if action == FILTER_ACTION_MOVE and not destination:
            return FILTER_MOVE_NO_DESTINATION

        # Validate regex patterns
        try:
            if subject_pattern:
                re.compile(subject_pattern)
            if from_pattern:
                re.compile(from_pattern)
        except re.error as e:
            return FILTER_INVALID_REGEX.format(error=e)

        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error

            messages = client.get_all_messages(folder=folder, limit=limit)
            if not messages:
                return json.dumps({
                    "dry_run": dry_run,
                    "matched": 0,
                    "total_scanned": 0,
                    "results": [],
                })

            results: list[dict[str, str]] = []
            for msg_id, email_msg in messages:
                subject = email_msg.subject or ""
                from_addr = email_msg.from_address or ""

                subject_match = (
                    bool(re.search(subject_pattern, subject, re.IGNORECASE))
                    if subject_pattern
                    else True
                )
                from_match = (
                    bool(re.search(from_pattern, from_addr, re.IGNORECASE))
                    if from_pattern
                    else True
                )

                if subject_match and from_match:
                    results.append({
                        "_id": str(msg_id),
                        "from": from_addr,
                        "subject": subject,
                        "date": email_msg.date or "",
                    })

            if not dry_run and results:
                client.client.select_folder(folder)
                for item in results:
                    eid = item["_id"]
                    if action == FILTER_ACTION_TRASH:
                        client.move_to_folder(eid, "Trash")
                    elif action == FILTER_ACTION_MOVE:
                        client.move_to_folder(eid, destination)

            return json.dumps({
                "dry_run": dry_run,
                "matched": len(results),
                "total_scanned": len(messages),
                "results": results,
            })
        finally:
            client.disconnect()

    def search_emails(self, query: str, folder: str = "INBOX", limit: int = 20) -> str:
        """Search emails by query string (searches From, Subject, Body).

        Uses server-side IMAP SUBJECT/FROM search first. Falls back to
        client-side filtering on the most recent *limit* emails when the
        server-side search returns nothing.
        """
        logger.info("search_emails: query=%r, folder=%r, limit=%d", query, folder, limit)
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                logger.warning("search_emails: folder validation failed: %s", error)
                return error

            # Server-side IMAP search for subject and from
            messages = client.get_messages(
                search_criteria=["OR", "SUBJECT", query, "FROM", query],
                folder=folder,
                limit=limit,
                include_attachments=False,
            )

            if messages:
                matches = list(messages)
                logger.info(
                    "search_emails: server-side search returned %d result(s)", len(matches)
                )
            else:
                logger.info("search_emails: server-side search returned nothing, falling back")
                # Fallback: client-side filtering on recent emails
                messages = client.get_messages(
                    search_criteria=["ALL"],
                    folder=folder,
                    limit=limit,
                    include_attachments=False,
                )
                if not messages:
                    logger.info("search_emails: no emails found in folder %r", folder)
                    return f"No emails found in {folder}."

                logger.info(
                    "search_emails: fetched %d email(s) for client-side filtering",
                    len(messages),
                )
                query_lower = query.lower()
                matches = []
                for msg_id, email_msg in messages:
                    from_addr = (email_msg.from_address or "").lower()
                    subject = (email_msg.subject or "").lower()
                    body = ""
                    with contextlib.suppress(Exception):
                        body = (email_msg.get_body(MIME_TEXT_PLAIN) or "").lower()

                    if (
                        query_lower in from_addr
                        or query_lower in subject
                        or query_lower in body
                    ):
                        matches.append((msg_id, email_msg))

                logger.info(
                    "search_emails: client-side filtering matched %d email(s)", len(matches)
                )

            if not matches:
                logger.info("search_emails: no matches for query=%r", query)
                return f"No emails matching '{query}' found."

            results = []
            for msg_id, email_msg in matches:
                results.append({
                    "_id": str(msg_id),
                    "from": email_msg.from_address or "",
                    "subject": email_msg.subject or "",
                    "date": email_msg.date or "",
                })
            logger.info("search_emails: returning %d result(s)", len(results))
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

    def move_email(
        self, email_id: str, destination_folder: str, source_folder: str = "INBOX"
    ) -> str:
        """Move an email to a different folder."""
        client = self._create_client()
        try:
            source_folder, error = self._resolve_folder(client, source_folder)
            if error:
                return error
            client.client.select_folder(source_folder)
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

    def get_meeting_info(self, email_id: str, folder: str = "INBOX") -> str:
        """Get meeting/calendar details from an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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

    def get_meeting_links(self, email_id: str, folder: str = "INBOX") -> str:
        """Extract meeting links (Teams, Zoom, Meet) from an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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

    def detect_invite_in_email(self, email_id: str, folder: str = "INBOX") -> str:
        """Check if an email contains a calendar invite."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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
                    if invite.ics_data:
                        sanitized = invite.ics_data.replace(b"\x00", b"")
                        info["ics_data"] = sanitized.decode("utf-8", errors="replace")
                    return json.dumps(info)
            return "Email not found."
        finally:
            client.disconnect()

    def send_rsvp_for_email(
        self, email_id: str, status: str = "ACCEPTED", folder: str = "INBOX"
    ) -> str:
        """Accept or decline a meeting invite by sending an RSVP."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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

    def draft_reply(
        self, email_id: str, reply_body: str, greeting: str = "", folder: str = "INBOX"
    ) -> str:
        """Save a reply draft to an email."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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
                    html_body = assemble_reply_html(
                        content, footer_html=self._settings.footer_html
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
        self, email_id: str, reply_body: str, greeting: str = "", folder: str = "INBOX"
    ) -> str:
        """Send a reply to an email directly via SMTP."""
        client = self._create_client()
        try:
            messages = client.get_all_messages(folder=folder)
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
                    html_body = assemble_reply_html(
                        content, footer_html=self._settings.footer_html
                    )

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
                    success = client.forward_email(
                        email_message=email_msg,
                        to_addresses=to_addresses,
                        sender_email=self._settings.from_address,
                        smtp_server=self._settings.smtp.server,
                        smtp_port=self._settings.smtp.port,
                        smtp_username=self._settings.smtp.username,
                        smtp_password=self._settings.smtp.password,
                        additional_message=additional_message,
                    )
                    if success:
                        return f"Email forwarded to {', '.join(to_addresses)}."
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
        """Save a forward draft preserving all attachments and inline images."""
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=True,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) == str(email_id):
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
                        logger.error("Error saving forward draft: %s", e)
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
