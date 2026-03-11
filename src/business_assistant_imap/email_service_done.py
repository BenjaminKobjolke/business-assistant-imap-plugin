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
    ) -> str:
        """Mark an email as done by moving it to a mapped folder.

        Looks up the sender in the database to find the target folder.
        If no mapping exists the caller must supply target_folder and mapping_type.
        """
        client = self._create_client()
        try:
            messages = client.get_messages(
                search_criteria=["ALL"],
                folder=folder,
                include_attachments=False,
            )
            for msg_id, email_msg in messages:
                if str(msg_id) != str(email_id):
                    continue

                sender = _extract_sender(email_msg.from_address or "")
                if not sender:
                    return "Could not determine sender address."

                mapping = database.get_folder_mapping(sender)

                # Case 1: no target_folder provided
                if not target_folder:
                    if mapping:
                        # Known mapping → move
                        return self._do_move(
                            client, email_id, mapping.folder, folder
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
                            client, email_id, target_folder, folder
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

                database.set_folder_mapping(
                    identifier, target_folder, mapping_type
                )
                return self._do_move(
                    client, email_id, target_folder, folder
                )

            return "Email not found."
        finally:
            client.disconnect()

    def _do_move(
        self,
        client: object,
        email_id: str,
        destination: str,
        source: str,
    ) -> str:
        """Move an email and return a success/failure message."""
        client.client.select_folder(source)
        success = client.move_to_folder(email_id, destination)
        if success:
            return json.dumps({
                "status": "done",
                "moved_to": destination,
            })
        return f"Failed to move email to '{destination}'."
