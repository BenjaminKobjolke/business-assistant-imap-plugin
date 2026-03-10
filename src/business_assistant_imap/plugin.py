"""Plugin registration — defines PydanticAI tools for email operations."""

from __future__ import annotations

import logging

from business_assistant.agent.deps import Deps
from business_assistant.plugins.registry import PluginInfo, PluginRegistry
from pydantic_ai import RunContext, Tool

from .config import load_email_settings
from .constants import (
    PLUGIN_DATA_EMAIL_SERVICE,
    PLUGIN_DESCRIPTION,
    PLUGIN_NAME,
    SYSTEM_PROMPT_EMAIL,
)
from .email_service import EmailService
from .greeting_builder import build_greeting

logger = logging.getLogger(__name__)


def _get_service(ctx: RunContext[Deps]) -> EmailService:
    """Retrieve the EmailService from plugin_data."""
    return ctx.deps.plugin_data[PLUGIN_DATA_EMAIL_SERVICE]


def _list_inbox(ctx: RunContext[Deps], limit: int = 20) -> str:
    """List recent emails from the inbox. Default limit: 20."""
    return _get_service(ctx).list_inbox(limit=limit)


def _show_email(ctx: RunContext[Deps], email_id: str, folder: str = "INBOX") -> str:
    """Show full details of a specific email by its ID.

    Use folder='Sent' for sent emails.
    """
    return _get_service(ctx).show_email(email_id, folder)


def _search_emails(ctx: RunContext[Deps], query: str) -> str:
    """Search emails by query string. Checks memory for aliases first.

    The query is matched against From, Subject, and Body fields.
    """
    memory = ctx.deps.memory
    alias = memory.get(query.lower())
    if alias:
        query = alias
    return _get_service(ctx).search_emails(query)


def _list_folders(ctx: RunContext[Deps]) -> str:
    """List all mailbox folders."""
    return _get_service(ctx).list_folders()


def _move_email(ctx: RunContext[Deps], email_id: str, destination_folder: str) -> str:
    """Move an email to a different folder."""
    return _get_service(ctx).move_email(email_id, destination_folder)


def _trash_email(ctx: RunContext[Deps], email_id: str) -> str:
    """Move an email to the Trash folder."""
    return _get_service(ctx).trash_email(email_id)


def _get_unread_count(ctx: RunContext[Deps]) -> str:
    """Get the number of unread emails in the inbox."""
    return _get_service(ctx).get_unread_count()


def _get_meeting_info(ctx: RunContext[Deps], email_id: str) -> str:
    """Get meeting/calendar details from an email containing ICS data."""
    return _get_service(ctx).get_meeting_info(email_id)


def _get_appointments(ctx: RunContext[Deps], folder: str = "INBOX") -> str:
    """List upcoming appointments from emails with ICS data in the given folder."""
    return _get_service(ctx).get_appointments(folder)


def _get_meeting_links(ctx: RunContext[Deps], email_id: str) -> str:
    """Extract meeting links (Teams, Zoom, Google Meet) from an email."""
    return _get_service(ctx).get_meeting_links(email_id)


def _detect_invite(ctx: RunContext[Deps], email_id: str) -> str:
    """Check if an email contains a calendar invite and show details."""
    return _get_service(ctx).detect_invite_in_email(email_id)


def _send_rsvp(ctx: RunContext[Deps], email_id: str, status: str = "ACCEPTED") -> str:
    """Accept or decline a meeting invite. Status: ACCEPTED, DECLINED, or TENTATIVE."""
    return _get_service(ctx).send_rsvp_for_email(email_id, status)


def _draft_reply(
    ctx: RunContext[Deps], email_id: str, reply_body: str, greeting: str = ""
) -> str:
    """Save a reply draft to an email in the Drafts folder."""
    return _get_service(ctx).draft_reply(email_id, reply_body, greeting)


def _send_reply(
    ctx: RunContext[Deps], email_id: str, reply_body: str, greeting: str = ""
) -> str:
    """Send a reply to an email directly via SMTP."""
    return _get_service(ctx).send_reply(email_id, reply_body, greeting)


def _search_sent_to(ctx: RunContext[Deps], email_address: str, limit: int = 3) -> str:
    """Search the Sent folder for recent emails to a specific address.

    Returns email body snippets so you can detect salutation patterns.
    """
    return _get_service(ctx).search_sent_to(email_address, limit)


def _build_greeting(ctx: RunContext[Deps], salutation: str = "", skip: bool = False) -> str:
    """Build a time-aware greeting. Returns 'Guten Morgen <salutation>' before 10 AM,
    'Hallo <salutation>' otherwise. Returns empty string if skip is True.
    """
    return build_greeting(salutation, skip)


def register(registry: PluginRegistry) -> None:
    """Register the IMAP plugin with the plugin registry.

    Reads IMAP/SMTP settings from environment. Skips registration
    if IMAP_SERVER is not configured.
    """
    email_settings = load_email_settings()
    if email_settings is None:
        logger.info("IMAP plugin: IMAP_SERVER not configured, skipping registration")
        return

    service = EmailService(email_settings)

    tools = [
        Tool(_list_inbox, name="list_inbox"),
        Tool(_show_email, name="show_email"),
        Tool(_search_emails, name="search_emails"),
        Tool(_list_folders, name="list_folders"),
        Tool(_move_email, name="move_email"),
        Tool(_trash_email, name="trash_email"),
        Tool(_get_unread_count, name="get_unread_count"),
        Tool(_get_meeting_info, name="get_meeting_info"),
        Tool(_get_appointments, name="get_appointments"),
        Tool(_get_meeting_links, name="get_meeting_links"),
        Tool(_detect_invite, name="detect_invite"),
        Tool(_send_rsvp, name="send_rsvp"),
        Tool(_draft_reply, name="draft_reply"),
        Tool(_send_reply, name="send_reply"),
        Tool(_search_sent_to, name="search_sent_to"),
        Tool(_build_greeting, name="build_greeting"),
    ]

    info = PluginInfo(
        name=PLUGIN_NAME,
        description=PLUGIN_DESCRIPTION,
        system_prompt_extra=SYSTEM_PROMPT_EMAIL,
    )

    registry.register(info, tools)
    registry.plugin_data[PLUGIN_DATA_EMAIL_SERVICE] = service

    logger.info("IMAP plugin registered with %d tools", len(tools))
