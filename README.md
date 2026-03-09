# Business Assistant IMAP Plugin

IMAP/SMTP email plugin for Business Assistant v2. Provides email management tools including inbox listing, search, meeting extraction, invite RSVP, draft composition, and reply sending.

## Setup

1. Copy `.env.example` to `.env` and configure IMAP/SMTP settings
2. Run `install.bat` to install dependencies
3. Add `business_assistant_imap` to the `PLUGINS` env var in the main project's `.env`

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `IMAP_SERVER` | IMAP server hostname | (required) |
| `IMAP_USERNAME` | IMAP username | (required) |
| `IMAP_PASSWORD` | IMAP password | (required) |
| `IMAP_PORT` | IMAP port | 993 |
| `IMAP_USE_SSL` | Use SSL for IMAP | true |
| `SMTP_SERVER` | SMTP server hostname | derived from IMAP |
| `SMTP_PORT` | SMTP port | 587 |
| `SMTP_USERNAME` | SMTP username | same as IMAP |
| `SMTP_PASSWORD` | SMTP password | same as IMAP |
| `EMAIL_FROM_ADDRESS` | Sender email address | same as IMAP username |

## Tools Provided

- **list_inbox** — List recent emails
- **show_email** — Show full email details
- **search_emails** — Search by query (memory-aware aliases)
- **list_folders** — List mailbox folders
- **move_email** — Move email to folder
- **trash_email** — Move email to Trash
- **get_unread_count** — Count unread emails
- **get_meeting_info** — Extract meeting details from ICS
- **get_appointments** — List upcoming appointments
- **get_meeting_links** — Extract Teams/Zoom/Meet URLs
- **detect_invite** — Check for calendar invites
- **send_rsvp** — Accept/decline meeting invites
- **draft_reply** — Save reply draft
- **send_reply** — Send reply via SMTP

## Development

```bash
tools\tests.bat
```

## Dependencies

- [imap-client-lib](../imap_client_python) — IMAP client library
- [business-assistant-v2](../business-assistant-v2) — Main project (for plugin types)
- [python-dateutil](https://github.com/dateutil/dateutil) — Date parsing
