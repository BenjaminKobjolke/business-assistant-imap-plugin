# Business Assistant IMAP Plugin - Development Guide

## Project Overview

IMAP/SMTP email plugin for Business Assistant v2. Source code in `src/business_assistant_imap/`.

## Commands

- `uv sync --all-extras` — Install dependencies
- `uv run pytest tests/ -v` — Run tests
- `uv run ruff check src/ tests/` — Lint
- `uv run mypy src/` — Type check

## Architecture

- `config.py` — ImapSettings + SmtpSettings (frozen dataclasses)
- `constants.py` — Plugin-specific string constants
- `meeting_parser.py` — ICS/VEVENT parsing, meeting link extraction
- `invite_handler.py` — Invite detection + RSVP handling
- `draft_builder.py` — Reply draft composition
- `email_service.py` — High-level email operations wrapping ImapClient
- `plugin.py` — Plugin registration + PydanticAI tool definitions
- `__init__.py` — Exposes `register()` as entry point

## Plugin Protocol

The plugin exposes `register(registry: PluginRegistry)` which:
1. Loads IMAP/SMTP settings from env vars
2. Skips registration if IMAP_SERVER not configured
3. Creates EmailService and registers 14 PydanticAI tools

## Rules

- Use objects for related values (DTOs/Settings)
- Centralize string constants in `constants.py`
- Tests are mandatory — use pytest with mocked ImapClient
- Use `spec=` with MagicMock
- Each email operation connects/disconnects per call (try/finally)
- Type hints on all public APIs
