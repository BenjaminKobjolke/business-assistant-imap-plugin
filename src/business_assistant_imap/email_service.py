"""EmailService — wraps ImapClient for all email operations."""

from __future__ import annotations

import contextlib
import difflib
import json
import logging
import re

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
from .email_service_compose import ComposeMixin, _extract_reply_address
from .email_service_done import DoneMixin
from .email_service_meeting import MeetingMixin

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = ["EmailService", "_extract_reply_address"]


class EmailService(MeetingMixin, ComposeMixin, DoneMixin):
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
            raise ConnectionError(
                f"Failed to connect to {self._account.server}"
            )
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
                folder, list(leaves.keys()),
                n=MAX_FOLDER_SUGGESTIONS, cutoff=0.4,
            )
            for leaf in fuzzy:
                full = leaves[leaf]
                if full not in suggestions:
                    suggestions.append(full)

        suggestions = suggestions[:MAX_FOLDER_SUGGESTIONS]

        if suggestions:
            lines = "\n".join(f"  - {s}" for s in suggestions)
            return folder, FOLDER_NOT_FOUND.format(
                folder=folder, suggestions=lines
            )
        return folder, FOLDER_NOT_FOUND_NO_SUGGESTIONS.format(folder=folder)

    def list_inbox(
        self, limit: int = 20, unread_only: bool = False
    ) -> str:
        """List recent emails from the inbox."""
        return self.list_messages("INBOX", limit=limit, unread_only=unread_only)

    def list_messages(
        self, folder: str = "INBOX", limit: int = 20,
        unread_only: bool = False,
    ) -> str:
        """List recent emails from a specific folder."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error

            if unread_only:
                messages = client.get_messages(
                    search_criteria=["UNSEEN"],
                    folder=folder,
                    limit=limit,
                    include_attachments=False,
                )
            else:
                messages = client.get_all_messages(
                    folder=folder, limit=limit
                )
            if not messages:
                return f"No emails found in {folder}."

            emails = []
            for msg_id, email_msg in messages:
                emails.append({
                    "_id": str(msg_id),
                    "from": email_msg.from_address or "(unknown)",
                    "subject": email_msg.subject or "(no subject)",
                    "date": email_msg.date or "",
                    "tags": email_msg.keywords,
                })
            return json.dumps({"emails": emails})
        finally:
            client.disconnect()

    def show_email(self, email_id: str, folder: str = "INBOX") -> str:
        """Show full details of a specific email."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            body = (
                email_msg.get_body(MIME_TEXT_PLAIN)
                or "(no text body)"
            )
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
                "tags": email_msg.keywords,
            })
        finally:
            client.disconnect()

    def get_html_body(self, email_id: str, folder: str = "INBOX") -> str:
        """Return the HTML body of an email, or empty string if not available."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=False,
            )
            if result is None:
                return ""
            msg_id, email_msg = result
            return email_msg.get_body(MIME_TEXT_HTML) or ""
        finally:
            client.disconnect()

    def get_attachment_url(
        self,
        email_id: str,
        filename: str,
        folder: str = "INBOX",
        ftp_service: object | None = None,
    ) -> str:
        """Upload a specific attachment via FTP and return a URL."""
        if not ftp_service:
            return "FTP upload not configured."

        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            for a in email_msg.attachments or []:
                if a.filename == filename:
                    try:
                        url = ftp_service.upload(
                            a.data, a.filename
                        )
                    except Exception:
                        logger.warning(
                            "FTP upload failed for %s",
                            a.filename,
                        )
                        return (
                            f"FTP upload failed for '{filename}'."
                        )
                    return json.dumps({
                        "filename": a.filename,
                        "url": url,
                        "content_type": a.content_type,
                    })
            return (
                f"Attachment '{filename}' not found in email."
            )
        finally:
            client.disconnect()

    def save_attachment(
        self,
        email_id: str,
        filename: str,
        destination_path: str,
        folder: str = "INBOX",
        filesystem_service: object | None = None,
    ) -> str:
        """Save an email attachment to the local filesystem."""
        if not filesystem_service:
            return "Filesystem service not configured."

        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            for a in email_msg.attachments or []:
                if a.filename == filename:
                    save_result = filesystem_service.write_binary(  # type: ignore[attr-defined]
                        destination_path, a.data,
                    )
                    return save_result
            return (
                f"Attachment '{filename}' not found in email."
            )
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

            messages = client.get_all_messages(
                folder=folder, limit=limit
            )
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
                    bool(re.search(
                        subject_pattern, subject, re.IGNORECASE
                    ))
                    if subject_pattern
                    else True
                )
                from_match = (
                    bool(re.search(
                        from_pattern, from_addr, re.IGNORECASE
                    ))
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

    def search_emails(
        self, query: str, folder: str = "INBOX", limit: int = 20,
        tag: str | None = None,
    ) -> str:
        """Search emails by query string (From, Subject, Body) and/or IMAP tag."""
        logger.info(
            "search_emails: query=%r, folder=%r, limit=%d, tag=%r",
            query, folder, limit, tag,
        )
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                logger.warning(
                    "search_emails: folder validation failed: %s", error
                )
                return error

            # Build search criteria
            if tag and query:
                criteria: list[str] = [
                    "KEYWORD", tag, "OR", "SUBJECT", query, "FROM", query,
                ]
            elif tag:
                criteria = ["KEYWORD", tag]
            else:
                criteria = ["OR", "SUBJECT", query, "FROM", query]

            # Server-side IMAP search
            messages = client.get_messages(
                search_criteria=criteria,
                folder=folder,
                limit=limit,
                include_attachments=False,
            )

            if messages:
                matches = list(messages)
                logger.info("search_emails: server-side returned %d", len(matches))
            elif tag:
                # Tag search is purely server-side; no client fallback
                logger.info("search_emails: no emails with tag=%r", tag)
                matches = []
            else:
                logger.info("search_emails: server-side empty, falling back")
                messages = client.get_messages(
                    search_criteria=["ALL"],
                    folder=folder,
                    limit=limit,
                    include_attachments=False,
                )
                if not messages:
                    logger.info("search_emails: no emails in %r", folder)
                    return f"No emails found in {folder}."

                logger.info("search_emails: filtering %d email(s)", len(messages))
                query_lower = query.lower()
                matches = []
                for msg_id, email_msg in messages:
                    from_addr = (
                        email_msg.from_address or ""
                    ).lower()
                    subject = (email_msg.subject or "").lower()
                    body = ""
                    with contextlib.suppress(Exception):
                        body = (
                            email_msg.get_body(MIME_TEXT_PLAIN) or ""
                        ).lower()

                    if (
                        query_lower in from_addr
                        or query_lower in subject
                        or query_lower in body
                    ):
                        matches.append((msg_id, email_msg))

                logger.info(
                    "search_emails: client-side matched %d email(s)",
                    len(matches),
                )

            if not matches:
                search_desc = f"tag '{tag}'" if tag else f"'{query}'"
                logger.info(
                    "search_emails: no matches for %s", search_desc
                )
                return f"No emails matching {search_desc} found."

            results = []
            for msg_id, email_msg in matches:
                results.append({
                    "_id": str(msg_id),
                    "from": email_msg.from_address or "",
                    "subject": email_msg.subject or "",
                    "date": email_msg.date or "",
                })
            logger.info(
                "search_emails: returning %d result(s)", len(results)
            )
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
        self,
        email_id: str,
        destination_folder: str,
        source_folder: str = "INBOX",
    ) -> str:
        """Move an email to a different folder."""
        client = self._create_client()
        try:
            source_folder, error = self._resolve_folder(
                client, source_folder
            )
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

    def mark_as_read(self, email_id: str, folder: str = "INBOX") -> str:
        """Mark an email as read (set \\Seen flag)."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error
            client.client.select_folder(folder)
            success = client.mark_as_read(email_id)
            if success:
                return "Email marked as read."
            return "Failed to mark email as read."
        finally:
            client.disconnect()

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

    def get_email_tags(self, email_id: str, folder: str = "INBOX") -> str:
        """Get all tags/keywords on a specific email."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error
            client.client.select_folder(folder)
            keywords = client.get_keywords(email_id)
            return json.dumps({"email_id": email_id, "tags": keywords})
        finally:
            client.disconnect()

    def add_email_tag(
        self, email_id: str, tag: str, folder: str = "INBOX"
    ) -> str:
        """Add a tag/keyword to an email."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error
            client.client.select_folder(folder)
            success = client.add_keyword(email_id, tag)
            if success:
                return f"Tag '{tag}' added to email."
            return f"Failed to add tag '{tag}'."
        finally:
            client.disconnect()

    def remove_email_tag(
        self, email_id: str, tag: str, folder: str = "INBOX"
    ) -> str:
        """Remove a tag/keyword from an email."""
        client = self._create_client()
        try:
            folder, error = self._resolve_folder(client, folder)
            if error:
                return error
            client.client.select_folder(folder)
            success = client.remove_keyword(email_id, tag)
            if success:
                return f"Tag '{tag}' removed from email."
            return f"Failed to remove tag '{tag}'."
        finally:
            client.disconnect()
