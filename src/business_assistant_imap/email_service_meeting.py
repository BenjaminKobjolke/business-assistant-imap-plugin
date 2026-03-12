"""Meeting and invite operations mixin for EmailService."""

from __future__ import annotations

import json
import logging
from datetime import date

from .invite_handler import detect_invite, send_rsvp
from .meeting_parser import (
    extract_ics_data,
    extract_meeting_links,
    extract_meeting_times,
    parse_vevent,
)

logger = logging.getLogger(__name__)


class MeetingMixin:
    """Meeting/invite methods — mixed into EmailService."""

    def get_meeting_info(self, email_id: str, folder: str = "INBOX") -> str:
        """Get meeting/calendar details from an email."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            dtstart, dtend = extract_meeting_times(email_msg)
            if dtstart is None:
                return "No meeting data found in this email."

            ics_data = extract_ics_data(email_msg)
            ics_text = (
                ics_data.decode("utf-8", errors="replace")
                if ics_data
                else None
            )
            parsed = parse_vevent(ics_text) if ics_text else None

            info: dict[str, str | None] = {
                "_id": str(msg_id),
                "start": dtstart.strftime("%Y-%m-%d %H:%M %Z"),
                "end": (
                    dtend.strftime("%Y-%m-%d %H:%M %Z")
                    if dtend
                    else None
                ),
                "organizer": None,
                "location": None,
            }
            if parsed:
                info["organizer"] = parsed.get("organizer")
                info["location"] = parsed.get("location")
            return json.dumps(
                {k: v for k, v in info.items() if v is not None}
            )
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
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            ics_data = extract_ics_data(email_msg)
            ics_text = (
                ics_data.decode("utf-8", errors="replace")
                if ics_data
                else None
            )
            links = extract_meeting_links(email_msg, ics_text)
            if not links:
                return "No meeting links found in this email."
            return json.dumps({
                "_id": str(msg_id),
                "links": [
                    {"type": lnk["type"], "url": lnk["url"]}
                    for lnk in links
                ],
            })
        finally:
            client.disconnect()

    def detect_invite_in_email(
        self, email_id: str, folder: str = "INBOX"
    ) -> str:
        """Check if an email contains a calendar invite."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            invite = detect_invite(str(msg_id), email_msg)
            if invite is None:
                return (
                    "This email does not contain a calendar invite."
                )
            info: dict[str, str | bool | None] = {
                "_id": str(msg_id),
                "subject": invite.summary or invite.subject,
            }
            if invite.dtstart:
                info["when"] = invite.dtstart.strftime(
                    "%Y-%m-%d %H:%M"
                )
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
                info["ics_data"] = sanitized.decode(
                    "utf-8", errors="replace"
                )
            return json.dumps(info)
        finally:
            client.disconnect()

    def send_rsvp_for_email(
        self, email_id: str, status: str = "ACCEPTED", folder: str = "INBOX"
    ) -> str:
        """Accept or decline a meeting invite by sending an RSVP."""
        client = self._create_client()
        try:
            result = client.get_message_by_id(
                email_id, folder=folder,
                include_attachments=True,
            )
            if result is None:
                return "Email not found."
            msg_id, email_msg = result

            invite = detect_invite(str(msg_id), email_msg)
            if invite is None:
                return (
                    "This email does not contain a calendar invite."
                )

            success = send_rsvp(
                smtp_settings=self._settings.smtp,
                invite=invite,
                user_email=self._settings.from_address,
                status=status.upper(),
            )
            if success:
                return (
                    f"RSVP ({status}) sent to "
                    f"{invite.organizer_email}."
                )
            return "Failed to send RSVP."
        finally:
            client.disconnect()
