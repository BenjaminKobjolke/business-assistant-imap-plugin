"""Plugin registration — defines PydanticAI tools for email operations."""

from __future__ import annotations

import logging
import re

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


_FOLDER_PREFIX_RE = re.compile(
    r'^folder:"([^"]+)"\s+(.+)$|^folder:(\S+)\s+(.+)$', re.IGNORECASE
)


def _extract_folder_from_query(query: str, folder: str) -> tuple[str, str]:
    """Extract folder from query if the agent used 'folder:name query' syntax.

    Supports both ``folder:Name query`` and ``folder:"Name With Spaces" query``.
    Only overrides the folder when the caller still has the default 'INBOX'.
    Returns (cleaned_query, folder).
    """
    if folder != "INBOX":
        return query, folder
    match = _FOLDER_PREFIX_RE.match(query.strip())
    if match:
        if match.group(1) is not None:
            return match.group(2).strip(), match.group(1)
        return match.group(4).strip(), match.group(3)
    return query, folder


def _get_service(ctx: RunContext[Deps]) -> EmailService:
    """Retrieve the EmailService from plugin_data."""
    return ctx.deps.plugin_data[PLUGIN_DATA_EMAIL_SERVICE]


def _list_inbox(ctx: RunContext[Deps], limit: int = 20) -> str:
    """List recent emails from the inbox. Default limit: 20."""
    logger.info("list_inbox: limit=%d", limit)
    return _get_service(ctx).list_inbox(limit=limit)


def _list_messages(ctx: RunContext[Deps], folder: str = "INBOX", limit: int = 20) -> str:
    """List recent emails from a specific mailbox folder.

    Use list_folders to discover available folder names.
    Examples: folder="Sent", folder="Company/Clients/ProjectName"
    """
    logger.info("list_messages: folder=%r limit=%d", folder, limit)
    return _get_service(ctx).list_messages(folder=folder, limit=limit)


def _show_email(ctx: RunContext[Deps], email_id: str, folder: str = "INBOX") -> str:
    """Show full details of a specific email by its ID.

    Use folder='Sent' for sent emails.
    """
    logger.info("show_email: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).show_email(email_id, folder)


def _get_attachment_url(
    ctx: RunContext[Deps], email_id: str, filename: str, folder: str = "INBOX"
) -> str:
    """Upload an email attachment to get a shareable URL.

    Use when user asks to see/download an attachment or image from an email.
    """
    logger.info(
        "get_attachment_url: email_id=%r filename=%r folder=%r",
        email_id, filename, folder,
    )
    ftp_service = ctx.deps.plugin_data.get("ftp_upload")
    return _get_service(ctx).get_attachment_url(
        email_id, filename, folder, ftp_service=ftp_service
    )


def _filter_emails(
    ctx: RunContext[Deps],
    subject_pattern: str = "",
    from_pattern: str = "",
    action: str = "trash",
    destination: str = "",
    folder: str = "INBOX",
    limit: int = 50,
    dry_run: bool = True,
) -> str:
    """Filter emails by subject/from regex patterns.

    Always use dry_run=True first to preview matches.
    Set dry_run=False only after user confirms.
    action: 'trash' (default) or 'move' (requires destination).
    Patterns use case-insensitive regex. Both patterns must match (AND logic).
    """
    logger.info(
        "filter_emails: subject=%r from=%r action=%r dry_run=%r folder=%r",
        subject_pattern, from_pattern, action, dry_run, folder,
    )
    return _get_service(ctx).filter_emails(
        subject_pattern=subject_pattern,
        from_pattern=from_pattern,
        action=action,
        destination=destination,
        folder=folder,
        limit=limit,
        dry_run=dry_run,
    )


def _search_emails(ctx: RunContext[Deps], query: str, folder: str = "INBOX") -> str:
    """Search emails by query string. Checks memory for aliases first.

    The query is matched against From, Subject, and Body fields.
    Use the folder parameter to search in a specific mailbox folder
    (e.g., folder="Company/Clients/ProjectName"). Do NOT put the folder
    name in the query — use the folder parameter instead.
    """
    # Fallback: extract folder from query if agent used "folder:name" syntax
    query, folder = _extract_folder_from_query(query, folder)

    memory = ctx.deps.memory
    alias = memory.get(query.lower())
    if alias:
        logger.info("search_emails: resolved alias %r -> %r", query, alias)
        query = alias
    logger.info("search_emails: query=%r folder=%r", query, folder)
    return _get_service(ctx).search_emails(query, folder=folder)


def _list_folders(ctx: RunContext[Deps]) -> str:
    """List all mailbox folders."""
    logger.info("list_folders: listing all mailbox folders")
    return _get_service(ctx).list_folders()


def _move_email(
    ctx: RunContext[Deps], email_id: str, destination_folder: str, source_folder: str = "INBOX"
) -> str:
    """Move an email to a different folder."""
    logger.info(
        "move_email: email_id=%r destination=%r source=%r",
        email_id, destination_folder, source_folder,
    )
    return _get_service(ctx).move_email(email_id, destination_folder, source_folder=source_folder)


def _trash_email(ctx: RunContext[Deps], email_id: str) -> str:
    """Move an email to the Trash folder."""
    logger.info("trash_email: email_id=%r", email_id)
    return _get_service(ctx).trash_email(email_id)


def _get_unread_count(ctx: RunContext[Deps]) -> str:
    """Get the number of unread emails in the inbox."""
    logger.info("get_unread_count")
    return _get_service(ctx).get_unread_count()


def _get_meeting_info(
    ctx: RunContext[Deps], email_id: str, folder: str = "INBOX"
) -> str:
    """Get meeting/calendar details from an email containing ICS data.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("get_meeting_info: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).get_meeting_info(email_id, folder)


def _get_appointments(ctx: RunContext[Deps], folder: str = "INBOX") -> str:
    """List upcoming appointments from emails with ICS data in the given folder."""
    logger.info("get_appointments: folder=%r", folder)
    return _get_service(ctx).get_appointments(folder)


def _get_meeting_links(
    ctx: RunContext[Deps], email_id: str, folder: str = "INBOX"
) -> str:
    """Extract meeting links (Teams, Zoom, Google Meet) from an email.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("get_meeting_links: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).get_meeting_links(email_id, folder)


def _detect_invite(
    ctx: RunContext[Deps], email_id: str, folder: str = "INBOX"
) -> str:
    """Check if an email contains a calendar invite and show details.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("detect_invite: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).detect_invite_in_email(email_id, folder)


def _send_rsvp(
    ctx: RunContext[Deps],
    email_id: str,
    status: str = "ACCEPTED",
    folder: str = "INBOX",
) -> str:
    """Accept or decline a meeting invite. Status: ACCEPTED, DECLINED, or TENTATIVE.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("send_rsvp: email_id=%r status=%r folder=%r", email_id, status, folder)
    return _get_service(ctx).send_rsvp_for_email(email_id, status, folder)


def _draft_reply(
    ctx: RunContext[Deps],
    email_id: str,
    reply_body: str,
    greeting: str = "",
    folder: str = "INBOX",
) -> str:
    """Save a reply draft to an email in the Drafts folder.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("draft_reply: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).draft_reply(email_id, reply_body, greeting, folder)


def _send_reply(
    ctx: RunContext[Deps],
    email_id: str,
    reply_body: str,
    greeting: str = "",
    folder: str = "INBOX",
) -> str:
    """Send a reply to an email directly via SMTP.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("send_reply: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).send_reply(email_id, reply_body, greeting, folder)


def _forward_email(
    ctx: RunContext[Deps],
    email_id: str,
    to_addresses: list[str],
    additional_message: str = "",
    folder: str = "INBOX",
) -> str:
    """Forward an email to one or more recipients, preserving all attachments and inline images.

    Use folder parameter if the email is not in INBOX (e.g., folder="Sent").
    """
    logger.info(
        "forward_email: email_id=%r to=%r folder=%r", email_id, to_addresses, folder
    )
    return _get_service(ctx).forward_email(
        email_id, to_addresses, additional_message, folder
    )


def _draft_forward(
    ctx: RunContext[Deps],
    email_id: str,
    to_address: str,
    additional_message: str = "",
    folder: str = "INBOX",
) -> str:
    """Save a forward draft preserving all attachments and inline images.

    Use folder parameter if the email is not in INBOX (e.g., folder="Sent").
    """
    logger.info(
        "draft_forward: email_id=%r to=%r folder=%r", email_id, to_address, folder
    )
    return _get_service(ctx).draft_forward(
        email_id, to_address, additional_message, folder
    )


def _search_sent_to(ctx: RunContext[Deps], email_address: str, limit: int = 3) -> str:
    """Search the Sent folder for recent emails to a specific address.

    Returns email body snippets so you can detect salutation patterns.
    """
    logger.info("search_sent_to: email_address=%r limit=%d", email_address, limit)
    return _get_service(ctx).search_sent_to(email_address, limit)


def _build_greeting(ctx: RunContext[Deps], salutation: str = "", skip: bool = False) -> str:
    """Build a time-aware greeting. Returns 'Guten Morgen <salutation>' before 10 AM,
    'Hallo <salutation>' otherwise. Returns empty string if skip is True.
    """
    logger.info("build_greeting: salutation=%r skip=%r", salutation, skip)
    return build_greeting(salutation, skip)


def register(registry: PluginRegistry) -> None:
    """Register the IMAP plugin with the plugin registry.

    Reads IMAP/SMTP settings from environment. Skips registration
    if IMAP_SERVER is not configured.
    """
    from business_assistant.config.log_setup import add_plugin_logging

    add_plugin_logging("imap", "business_assistant_imap")

    email_settings = load_email_settings()
    if email_settings is None:
        logger.info("IMAP plugin: IMAP_SERVER not configured, skipping registration")
        return

    service = EmailService(email_settings)

    tools = [
        Tool(_list_inbox, name="list_inbox"),
        Tool(_list_messages, name="list_messages"),
        Tool(_show_email, name="show_email"),
        Tool(_get_attachment_url, name="get_attachment_url"),
        Tool(_filter_emails, name="filter_emails"),
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
        Tool(_forward_email, name="forward_email"),
        Tool(_draft_forward, name="draft_forward"),
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
