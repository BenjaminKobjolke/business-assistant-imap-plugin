"""Done-marking mixin for EmailService — moves emails to learned folders."""

from __future__ import annotations

import json
import logging
import re

from .database import Database

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"<([^>]+)>")


def _extract_sender(from_address: str) -> str:
    """Extract bare email address from a From header value."""
    match = _EMAIL_RE.search(from_address)
    if match:
        return match.group(1).lower()
    return from_address.strip().lower()


class DoneMixin:
    """Mark-as-done methods — mixed into EmailService."""

    def mark_as_done(
        self,
        email_id: str,
        database: Database,
        target_folder: str = "",
        mapping_type: str = "",
        folder: str = "INBOX",
        confirm: bool = False,
    ) -> str:
        """Mark an email as done by moving it to a mapped folder.

        Looks up the sender in the database to find the target folder.
        If no mapping exists the caller must supply target_folder, mapping_type,
        and confirm=True (to prevent accidental wrong folder selection).
        """
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=False,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            sender = _extract_sender(email_msg.from_address or "")
            if not sender:
                return "Could not determine sender address."

            # Extract Message-ID for post-move UID lookup
            message_id_header = ""
            if hasattr(email_msg, "raw_message") and email_msg.raw_message:
                message_id_header = email_msg.raw_message.get("Message-ID", "")

            mapping = database.get_folder_mapping(sender)

            # Case 1: no target_folder provided
            if not target_folder:
                if mapping:
                    # Known mapping → move
                    return self._do_move(
                        client, email_id, mapping.folder, folder,
                        message_id_header,
                    )
                return (
                    f"No target folder configured for {sender}. "
                    "Please call again with target_folder and "
                    "mapping_type ('person' or 'company')."
                )

            # Case 2: target_folder provided without mapping_type
            if not mapping_type:
                if mapping:
                    # Update existing mapping's folder, keep type
                    database.set_folder_mapping(
                        mapping.identifier, target_folder, mapping.mapping_type
                    )
                    return self._do_move(
                        client, email_id, target_folder, folder,
                        message_id_header,
                    )
                return (
                    "Please specify mapping_type: 'person' "
                    "(only this exact email) or 'company' "
                    "(all emails from @domain)."
                )

            # Case 3: target_folder + mapping_type provided
            if mapping_type == "person":
                identifier = sender
            elif mapping_type == "company":
                domain = sender.split("@")[-1] if "@" in sender else ""
                if not domain:
                    return "Cannot determine domain from sender address."
                identifier = f"@{domain}"
            else:
                return (
                    f"Invalid mapping_type '{mapping_type}'. "
                    "Use 'person' or 'company'."
                )

            # New mapping requires confirm=True to prevent wrong folder
            if not mapping and not confirm:
                return (
                    f"No existing rule for {sender}. "
                    f"Please confirm: create '{mapping_type}' rule "
                    f"'{identifier}' -> '{target_folder}'? "
                    "Verify the folder with the user, then call again "
                    "with confirm=True."
                )

            database.set_folder_mapping(
                identifier, target_folder, mapping_type
            )
            return self._do_move(
                client, email_id, target_folder, folder,
                message_id_header,
            )
        finally:
            client.disconnect()

    def _do_move(
        self,
        client: object,
        email_id: str,
        destination: str,
        source: str,
        message_id_header: str = "",
    ) -> str:
        """Move an email and return a success/failure message.

        After a successful move, attempts to find the new UID in the
        destination folder by searching for the Message-ID header.
        """
        client.client.select_folder(source)
        success = client.move_to_folder(email_id, destination)
        if success:
            result: dict = {"status": "done", "moved_to": destination}
            if message_id_header:
                try:
                    client.client.select_folder(destination)
                    uids = client.client.search(
                        ["HEADER", "Message-ID", message_id_header]
                    )
                    if uids:
                        result["new_email_id"] = str(uids[-1])
                except Exception:
                    logger.debug(
                        "Could not resolve new UID after move to %s",
                        destination,
                    )
            return json.dumps(result)
        return f"Failed to move email to '{destination}'."
