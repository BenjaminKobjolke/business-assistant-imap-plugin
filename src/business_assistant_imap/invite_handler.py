"""Meeting invite detection and RSVP handling.

Ported from imap-ai-assistant invite_processor.py and invite_rsvp.py.
"""

from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText

from .config import SmtpSettings
from .meeting_parser import extract_ics_data, parse_vevent

logger = logging.getLogger(__name__)


@dataclass
class ParsedInvite:
    """Holds parsed data from a calendar invite email."""

    message_id: str
    subject: str
    ics_data: bytes
    uid: str | None
    summary: str | None
    dtstart: datetime | None
    dtend: datetime | None
    organizer: str | None
    organizer_email: str | None
    location: str | None
    method: str | None

    @property
    def is_cancellation(self) -> bool:
        """Whether this invite is a METHOD:CANCEL cancellation."""
        return bool(self.method and self.method.upper() == "CANCEL")


def detect_invite(message_id: str, email_message: object) -> ParsedInvite | None:
    """Check whether email_message contains ICS data and return a parsed invite."""
    ics_data = extract_ics_data(email_message)
    if ics_data is None:
        return None

    details = parse_invite_details(ics_data)
    subject = getattr(email_message, "subject", "(no subject)") or "(no subject)"

    return ParsedInvite(
        message_id=message_id,
        subject=subject,
        ics_data=ics_data,
        uid=details.get("uid"),
        summary=details.get("summary"),
        dtstart=details.get("dtstart"),
        dtend=details.get("dtend"),
        organizer=details.get("organizer"),
        organizer_email=details.get("organizer_email"),
        location=details.get("location"),
        method=details.get("method"),
    )


def parse_invite_details(ics_data: bytes) -> dict:
    """Parse ICS data using the icalendar library with regex fallback."""
    result: dict = {}
    try:
        from icalendar import Calendar

        cal = Calendar.from_ical(ics_data)
        result["method"] = str(cal.get("method", "")) or None

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            uid = component.get("uid")
            if uid:
                result["uid"] = str(uid)

            summary = component.get("summary")
            if summary:
                result["summary"] = str(summary)

            location = component.get("location")
            if location:
                result["location"] = str(location)

            dtstart = component.get("dtstart")
            if dtstart:
                dt = dtstart.dt
                if isinstance(dt, datetime):
                    result["dtstart"] = dt
                else:
                    result["dtstart"] = datetime(dt.year, dt.month, dt.day)

            dtend = component.get("dtend")
            if dtend:
                dt = dtend.dt
                if isinstance(dt, datetime):
                    result["dtend"] = dt
                else:
                    result["dtend"] = datetime(dt.year, dt.month, dt.day)

            organizer = component.get("organizer")
            if organizer:
                org_email = str(organizer).replace("mailto:", "").replace("MAILTO:", "")
                result["organizer_email"] = org_email
                cn = organizer.params.get("CN", "") if hasattr(organizer, "params") else ""
                result["organizer"] = str(cn) if cn else org_email

            break

    except Exception as e:
        logger.warning("Failed to parse ICS with icalendar library: %s", e)
        try:
            ics_text = ics_data.decode("utf-8", errors="replace")
            parsed = parse_vevent(ics_text)
            if parsed:
                result["dtstart"] = parsed.get("dtstart")
                result["dtend"] = parsed.get("dtend")
                result["organizer"] = parsed.get("organizer")
                result["location"] = parsed.get("location")

                uid_m = re.search(r"UID[:]([^\r\n]+)", ics_text)
                if uid_m:
                    result["uid"] = uid_m.group(1).strip()
                summary_m = re.search(r"SUMMARY[:]([^\r\n]+)", ics_text)
                if summary_m:
                    result["summary"] = summary_m.group(1).strip()
        except Exception as fallback_err:
            logger.error("Fallback ICS parsing also failed: %s", fallback_err)

    return result


def build_rsvp_ics(invite: ParsedInvite, user_email: str, status: str = "ACCEPTED") -> str:
    """Build a METHOD:REPLY ICS string with the given PARTSTAT."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Business Assistant//EN",
        "METHOD:REPLY",
        "BEGIN:VEVENT",
    ]

    if invite.uid:
        lines.append(f"UID:{invite.uid}")
    if invite.dtstart:
        lines.append(f"DTSTART:{invite.dtstart.strftime('%Y%m%dT%H%M%SZ')}")
    if invite.dtend:
        lines.append(f"DTEND:{invite.dtend.strftime('%Y%m%dT%H%M%SZ')}")
    if invite.summary:
        lines.append(f"SUMMARY:{invite.summary}")
    if invite.organizer_email:
        lines.append(f"ORGANIZER:mailto:{invite.organizer_email}")

    now_utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines.append(f"DTSTAMP:{now_utc}")
    lines.append("SEQUENCE:0")

    lines.append(
        f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT"
        f";PARTSTAT={status};CN={user_email}:mailto:{user_email}"
    )
    lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    return "\r\n".join(lines)


def build_rsvp_message(
    invite: ParsedInvite, user_email: str, status: str = "ACCEPTED"
) -> MIMEMultipart:
    """Build an iTIP REPLY MIME message for an RSVP."""
    reply_ics = build_rsvp_ics(invite, user_email, status)
    subject = f"{status.capitalize()}: {invite.summary or invite.subject}"
    body_html = (
        '<div style="font-family: Arial, sans-serif; font-size: 14px;">'
        f"<p>{status.capitalize()}: {invite.summary or invite.subject}</p>"
        "</div>"
    )

    msg = MIMEMultipart("mixed")
    msg["From"] = user_email
    msg["To"] = invite.organizer_email or ""
    msg["Subject"] = subject

    html_part = MIMEText(body_html, "html")
    msg.attach(html_part)

    cal_part = MIMENonMultipart("text", "calendar", charset="utf-8", method="REPLY")
    cal_part.set_payload(reply_ics.encode("utf-8"))
    cal_part["Content-Transfer-Encoding"] = "8bit"
    cal_part.add_header("Content-Disposition", "inline", filename="invite.ics")
    msg.attach(cal_part)

    return msg


def send_rsvp(
    smtp_settings: SmtpSettings,
    invite: ParsedInvite,
    user_email: str,
    status: str = "ACCEPTED",
) -> bool:
    """Send an iTIP RSVP directly via SMTP."""
    if not invite.organizer_email:
        logger.warning("No organizer email found, cannot send RSVP")
        return False

    try:
        msg = build_rsvp_message(invite, user_email, status)

        server = smtplib.SMTP(smtp_settings.server, smtp_settings.port)
        server.starttls()
        server.login(smtp_settings.username, smtp_settings.password)
        server.sendmail(user_email, invite.organizer_email, msg.as_string())
        server.quit()

        logger.info("RSVP (%s) sent to %s", status, invite.organizer_email)
        return True
    except Exception as e:
        logger.error("Failed to send RSVP: %s", e)
        return False
