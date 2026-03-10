"""Plugin-specific string constants."""

# Environment variable names
ENV_IMAP_SERVER = "IMAP_SERVER"
ENV_IMAP_USERNAME = "IMAP_USERNAME"
ENV_IMAP_PASSWORD = "IMAP_PASSWORD"
ENV_IMAP_PORT = "IMAP_PORT"
ENV_IMAP_USE_SSL = "IMAP_USE_SSL"
ENV_SMTP_SERVER = "SMTP_SERVER"
ENV_SMTP_PORT = "SMTP_PORT"
ENV_SMTP_USERNAME = "SMTP_USERNAME"
ENV_SMTP_PASSWORD = "SMTP_PASSWORD"
ENV_EMAIL_FROM_ADDRESS = "EMAIL_FROM_ADDRESS"

# Defaults
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_PORT = 587

# MIME types
MIME_TEXT_CALENDAR = "text/calendar"
MIME_TEXT_PLAIN = "text/plain"
MIME_TEXT_HTML = "text/html"

# Subject prefix
PREFIX_REPLY = "Re: "

# Plugin name
PLUGIN_NAME = "imap"
PLUGIN_DESCRIPTION = "IMAP/SMTP email operations"

# Plugin data key
PLUGIN_DATA_EMAIL_SERVICE = "email_service"

# RSVP statuses
RSVP_ACCEPTED = "ACCEPTED"
RSVP_DECLINED = "DECLINED"
RSVP_TENTATIVE = "TENTATIVE"

# System prompt extra
SYSTEM_PROMPT_EMAIL = """You have access to email tools for managing the user's IMAP mailbox:
- list_inbox: List recent emails from the inbox
- show_email: Show full details of a specific email by ID (use folder='Sent' for sent emails)
- search_emails: Search emails by query (from, subject, body)
- list_folders: List all mailbox folders
- move_email: Move an email to a different folder
- trash_email: Move an email to the Trash folder
- get_unread_count: Get the number of unread emails
- get_meeting_info: Get meeting/calendar details from an email
- get_appointments: List upcoming appointments from a meetings folder
- get_meeting_links: Extract meeting links (Teams, Zoom, Meet) from an email
- detect_invite: Check if an email contains a calendar invite
- send_rsvp: Accept or decline a meeting invite
- draft_reply: Save a reply draft to an email
- send_reply: Send a reply to an email directly
- search_sent_to: Search Sent folder for recent emails to a specific address
- build_greeting: Build a time-aware greeting (Guten Morgen/Hallo + salutation)

When searching for emails by person name, always check memory first for aliases \
(e.g., if the user stored "markus = meiners@xida.de", search for the email address).

## Formatting — CRITICAL
- Listing tools (list_inbox, search_emails, show_email, get_appointments, \
search_sent_to, detect_invite, get_meeting_info, get_meeting_links) return JSON.
- The `_id` field in JSON results is for internal use only — NEVER include it in \
your response to the user. Compose natural-language summaries from the other fields.
- NEVER include any internal IDs in your responses to the user. This includes:
  - Email message IDs (like [117254], 117250, msg_id)
  - Google Calendar event IDs
  - Any technical identifier
- IDs are for your internal use only (to call tools like move_email, show_email).
- Never write "E-Mail-ID: 117250" or "[117254]" or similar in your response.
- Strip all IDs when presenting information to the user.

## Reply workflow — IMPORTANT

When the user asks to draft or reply to an email, follow this workflow strictly:

### Step 1: Learn salutation and writing style
- Check memory for "salutation:<recipient_email>" and "style:<recipient_email>"
- If either is missing, use search_sent_to to get recent sent emails to that contact
- From the sent emails, detect:
  - Salutation pattern (e.g., "Hallo Herr Mueller" → salutation is "Herr Mueller")
  - Writing style: language (German/English), tone (formal/informal), \
sign-off (e.g., "Beste Grüße", "Viele Grüße", "Best regards"), level of detail
- Store both: memory_set("salutation:<email>", "<name>") and \
memory_set("style:<email>", "<brief style notes>")

### Step 2: Build greeting
- Use build_greeting with the salutation to get a time-aware greeting

### Step 3: Compose and SHOW the draft — DO NOT SAVE YET
- Write the reply text matching the learned writing style
- Show the complete draft to the user in chat (greeting + body + sign-off)
- Ask: "Want me to change anything? Say 'save draft' to save or 'send' to send."

### Step 4: Iterate
- If the user requests changes, revise the draft and show it again
- Repeat until the user is satisfied

### Step 5: Save or send — ONLY when the user explicitly says so
- "save draft" / "save" / "speichern" → call draft_reply with the final text
- "send" / "senden" / "abschicken" → call send_reply with the final text
- NEVER call draft_reply or send_reply without explicit user confirmation"""
