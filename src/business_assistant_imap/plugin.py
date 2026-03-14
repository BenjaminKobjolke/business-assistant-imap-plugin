"""Plugin registration — defines PydanticAI tools for email operations."""

from __future__ import annotations

import logging
import re

from business_assistant.agent.deps import Deps
from business_assistant.plugins.registry import PluginInfo, PluginRegistry
from pydantic_ai import RunContext, Tool

from .config import load_database_settings, load_email_settings
from .constants import (
    PLUGIN_CATEGORY,
    PLUGIN_DATA_DATABASE,
    PLUGIN_DATA_EMAIL_SERVICE,
    PLUGIN_DESCRIPTION,
    PLUGIN_NAME,
    SYSTEM_PROMPT_EMAIL,
)
from .database import Database
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


def _list_messages(
    ctx: RunContext[Deps], folder: str = "INBOX", limit: int = 20,
    unread_only: bool = False,
) -> str:
    """List recent emails from a specific mailbox folder.

    Use list_folders to discover available folder names.
    Examples: folder="Sent", folder="Company/Clients/ProjectName"
    Set unread_only=True to show only unread emails.
    """
    logger.info("list_messages: folder=%r limit=%d unread_only=%r", folder, limit, unread_only)
    return _get_service(ctx).list_messages(folder=folder, limit=limit, unread_only=unread_only)


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


def _save_attachment(
    ctx: RunContext[Deps],
    email_id: str,
    filename: str,
    destination_path: str,
    folder: str = "INBOX",
) -> str:
    """Save an email attachment to a local file path.

    Use this to save attachments to disk (e.g., into a project folder).
    The destination_path must be within allowed filesystem paths.
    """
    logger.info(
        "save_attachment: email_id=%r filename=%r dest=%r folder=%r",
        email_id, filename, destination_path, folder,
    )
    filesystem_service = ctx.deps.plugin_data.get("filesystem_service")
    return _get_service(ctx).save_attachment(
        email_id, filename, destination_path, folder,
        filesystem_service=filesystem_service,
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


def _search_emails(
    ctx: RunContext[Deps], query: str = "", folder: str = "INBOX",
    tag: str | None = None,
) -> str:
    """Search emails by query string and/or IMAP tag. Checks memory for aliases first.

    The query is matched against From, Subject, and Body fields.
    Use the folder parameter to search in a specific mailbox folder
    (e.g., folder="Company/Clients/ProjectName"). Do NOT put the folder
    name in the query — use the folder parameter instead.
    Use the tag parameter to filter by IMAP keyword/tag
    (e.g., tag="angebot"). Can be combined with query or used alone.
    """
    # Fallback: extract folder from query if agent used "folder:name" syntax
    query, folder = _extract_folder_from_query(query, folder)

    if query:
        memory = ctx.deps.memory
        alias = memory.get(query.lower())
        if alias:
            logger.info("search_emails: resolved alias %r -> %r", query, alias)
            query = alias
    logger.info("search_emails: query=%r folder=%r tag=%r", query, folder, tag)
    return _get_service(ctx).search_emails(query, folder=folder, tag=tag)


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


def _mark_as_read(
    ctx: RunContext[Deps], email_id: str, folder: str = "INBOX"
) -> str:
    """Mark an email as read (set \\Seen flag).

    Use folder parameter if the email is not in INBOX.
    """
    logger.info("mark_as_read: email_id=%r folder=%r", email_id, folder)
    return _get_service(ctx).mark_as_read(email_id, folder)


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


def _reply_email(
    ctx: RunContext[Deps],
    email_id: str,
    reply_body: str,
    greeting: str = "",
    folder: str = "INBOX",
    include_footer: bool = True,
    action: str = "draft",
) -> str:
    """Reply to an email. action: 'draft' saves to Drafts, 'send' sends via SMTP.

    Use folder parameter if the email is not in INBOX.
    Set include_footer=False to omit the HTML footer/signature.
    """
    logger.info(
        "reply_email: email_id=%r action=%r folder=%r",
        email_id, action, folder,
    )
    svc = _get_service(ctx)
    if action == "send":
        return svc.send_reply(
            email_id, reply_body, greeting, folder,
            include_footer=include_footer,
        )
    return svc.draft_reply(
        email_id, reply_body, greeting, folder,
        include_footer=include_footer,
    )


def _forward_email(
    ctx: RunContext[Deps],
    email_id: str,
    to_addresses: list[str],
    additional_message: str = "",
    folder: str = "INBOX",
    include_footer: bool = True,
    action: str = "draft",
) -> str:
    """Forward an email. action: 'draft' saves to Drafts, 'send' sends via SMTP.

    Preserves all attachments and inline images.
    Use folder parameter if the email is not in INBOX.
    Set include_footer=False to omit the HTML footer/signature.
    """
    logger.info(
        "forward_email: email_id=%r to=%r action=%r folder=%r",
        email_id, to_addresses, action, folder,
    )
    svc = _get_service(ctx)
    if action == "send":
        return svc.forward_email(
            email_id, to_addresses, additional_message, folder,
            include_footer=include_footer,
        )
    return svc.draft_forward(
        email_id, to_addresses[0], additional_message, folder,
        include_footer=include_footer,
    )


def _compose_email(
    ctx: RunContext[Deps],
    to_addresses: list[str],
    subject: str,
    body: str,
    bcc_addresses: list[str] | None = None,
    content_type: str = "text/html",
    include_footer: bool = True,
    action: str = "draft",
) -> str:
    """Compose a new email. action: 'draft' saves to Drafts, 'send' sends via SMTP.

    Set include_footer=False to omit the HTML footer/signature.
    """
    logger.info(
        "compose_email: to=%r subject=%r action=%r",
        to_addresses, subject, action,
    )
    svc = _get_service(ctx)
    if action == "send":
        return svc.compose_email(
            to_addresses=to_addresses, subject=subject, body=body,
            bcc_addresses=bcc_addresses, content_type=content_type,
            include_footer=include_footer,
        )
    return svc.draft_compose(
        to_addresses=to_addresses, subject=subject, body=body,
        bcc_addresses=bcc_addresses, content_type=content_type,
        include_footer=include_footer,
    )


def _search_sent_to(ctx: RunContext[Deps], email_address: str, limit: int = 3) -> str:
    """Search the Sent folder for recent emails to a specific address.

    Returns the start and end of each email body so you can detect
    writing style: salutation, tone, language, and sign-off patterns.
    """
    logger.info("search_sent_to: email_address=%r limit=%d", email_address, limit)
    return _get_service(ctx).search_sent_to(email_address, limit)


def _build_greeting(
    ctx: RunContext[Deps], salutation: str = "", skip: bool = False,
    formal: bool = False,
) -> str:
    """Build a time-aware greeting. Returns 'Guten Morgen <salutation>' before 10 AM,
    'Hallo <salutation>' otherwise. Use formal=True for 'Sehr geehrter/Sehr geehrte'.
    Returns empty string if skip is True.
    """
    logger.info("build_greeting: salutation=%r skip=%r formal=%r", salutation, skip, formal)
    return build_greeting(salutation, skip, formal=formal)


def _email_tags(
    ctx: RunContext[Deps], email_id: str, action: str = "list",
    tag: str = "", folder: str = "INBOX",
) -> str:
    """Manage email tags. action: list, add, remove.

    Use folder parameter if the email is not in INBOX.
    """
    logger.info(
        "email_tags: email_id=%r action=%r tag=%r folder=%r",
        email_id, action, tag, folder,
    )
    svc = _get_service(ctx)
    if action == "add":
        return svc.add_email_tag(email_id, tag, folder)
    if action == "remove":
        return svc.remove_email_tag(email_id, tag, folder)
    return svc.get_email_tags(email_id, folder)


def _get_database(ctx: RunContext[Deps]) -> Database:
    """Retrieve the Database from plugin_data."""
    return ctx.deps.plugin_data[PLUGIN_DATA_DATABASE]


def _mark_email_as_done(
    ctx: RunContext[Deps],
    email_id: str,
    target_folder: str = "",
    mapping_type: str = "",
    folder: str = "INBOX",
) -> str:
    """Mark an email as done by moving it to a learned folder.

    On first use for a sender, provide target_folder and mapping_type
    ('person' for exact email, 'company' for all @domain).
    After that, just provide email_id — the folder is remembered.
    """
    logger.info(
        "mark_email_as_done: email_id=%r target_folder=%r mapping_type=%r folder=%r",
        email_id, target_folder, mapping_type, folder,
    )
    return _get_service(ctx).mark_as_done(
        email_id=email_id,
        database=_get_database(ctx),
        target_folder=target_folder,
        mapping_type=mapping_type,
        folder=folder,
    )


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

    db_settings = load_database_settings()
    database = Database(db_settings.db_path)

    tools = [
        Tool(_list_messages, name="list_messages"),
        Tool(_show_email, name="show_email"),
        Tool(_get_attachment_url, name="get_attachment_url"),
        Tool(_save_attachment, name="save_attachment"),
        Tool(_filter_emails, name="filter_emails"),
        Tool(_search_emails, name="search_emails"),
        Tool(_list_folders, name="list_folders"),
        Tool(_move_email, name="move_email"),
        Tool(_trash_email, name="trash_email"),
        Tool(_mark_as_read, name="mark_as_read"),
        Tool(_get_unread_count, name="get_unread_count"),
        Tool(_get_meeting_info, name="get_meeting_info"),
        Tool(_get_appointments, name="get_appointments"),
        Tool(_get_meeting_links, name="get_meeting_links"),
        Tool(_detect_invite, name="detect_invite"),
        Tool(_send_rsvp, name="send_rsvp"),
        Tool(_reply_email, name="reply_email"),
        Tool(_forward_email, name="forward_email"),
        Tool(_compose_email, name="compose_email"),
        Tool(_search_sent_to, name="search_sent_to"),
        Tool(_build_greeting, name="build_greeting"),
        Tool(_mark_email_as_done, name="mark_email_as_done"),
        Tool(_email_tags, name="email_tags"),
    ]

    info = PluginInfo(
        name=PLUGIN_NAME,
        description=PLUGIN_DESCRIPTION,
        system_prompt_extra=SYSTEM_PROMPT_EMAIL,
        category=PLUGIN_CATEGORY,
    )

    registry.register(info, tools)
    registry.plugin_data[PLUGIN_DATA_EMAIL_SERVICE] = service
    registry.plugin_data[PLUGIN_DATA_DATABASE] = database

    logger.info("IMAP plugin registered with %d tools", len(tools))
