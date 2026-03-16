"""Time-aware greeting builder for email replies."""

from __future__ import annotations

from datetime import datetime

from .constants import (
    GREETING_FORMAL_FRAU,
    GREETING_FORMAL_GENERIC,
    GREETING_FORMAL_HERR,
)

GREETING_MORNING = "Guten Morgen"
GREETING_DEFAULT = "Hallo"
GREETING_MORNING_HOUR_LIMIT = 10


def build_greeting(
    salutation: str = "",
    skip: bool = False,
    formal: bool = False,
    reference_hour: int | None = None,
) -> str:
    """Build a time-aware greeting string.

    Returns "Guten Morgen <salutation>" before 10 AM, "Hallo <salutation>" otherwise.
    When *formal* is True, returns "Sehr geehrter/Sehr geehrte <salutation>" regardless
    of time. Returns empty string if *skip* is True.

    When *reference_hour* is provided it overrides ``datetime.now().hour``.
    This is used by the Send Later feature so that greetings match the
    scheduled delivery time rather than the draft-creation time.
    """
    if skip:
        return ""
    if formal:
        if salutation.startswith("Herr"):
            return f"{GREETING_FORMAL_HERR} {salutation}"
        if salutation.startswith("Frau"):
            return f"{GREETING_FORMAL_FRAU} {salutation}"
        return GREETING_FORMAL_GENERIC
    hour = reference_hour if reference_hour is not None else datetime.now().hour
    prefix = GREETING_MORNING if hour < GREETING_MORNING_HOUR_LIMIT else GREETING_DEFAULT
    if salutation:
        return f"{prefix} {salutation}"
    return prefix
