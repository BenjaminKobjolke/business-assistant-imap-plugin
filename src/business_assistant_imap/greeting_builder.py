"""Time-aware greeting builder for email replies."""

from __future__ import annotations

from datetime import datetime

GREETING_MORNING = "Guten Morgen"
GREETING_DEFAULT = "Hallo"
GREETING_MORNING_HOUR_LIMIT = 10


def build_greeting(salutation: str = "", skip: bool = False) -> str:
    """Build a time-aware greeting string.

    Returns "Guten Morgen <salutation>" before 10 AM, "Hallo <salutation>" otherwise.
    Returns empty string if *skip* is True.
    """
    if skip:
        return ""
    now = datetime.now()
    prefix = GREETING_MORNING if now.hour < GREETING_MORNING_HOUR_LIMIT else GREETING_DEFAULT
    if salutation:
        return f"{prefix} {salutation}"
    return prefix
