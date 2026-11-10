# Tosint Agent Guidelines

## Project and Scope

Tosint is a Python CLI for Telegram OSINT investigations. Bot API requests
provide preliminary bot, chat, and administrator intelligence. Optional message
and attachment acquisition uses Pyrofork through the `pyrogram` import namespace.

Read the relevant code, tests, and README before editing. Keep changes scoped
to the request; do not combine bug fixes with unrelated refactors or dependency
upgrades. For review-only requests, report findings without editing files.

Write code comments, CLI output, documentation, and commit messages in English.
Keep the README minimal and readable; avoid decorative formatting and repetitive
examples. Update it when CLI behavior, defaults, or export formats change.

## Repository Layout

- `tosint.py`: CLI parsing, Bot API helpers, session handling, acquisition, and exports.
- `tests/`: offline regression tests using standard-library `unittest` and mocks.
- `requirements.txt`: pinned runtime dependencies; use the project virtual environment.
- `README.md`: user-facing installation, CLI reference, and operational limitations.
- `.env`, `sessions/`, `downloads/`, and `cover/`: local data, not public source.

Preserve unrelated work and untracked files, including local command scripts.
Never stage credentials, session databases, acquired evidence, or private images.
Do not run or import third-party disclosure scripts or downloaded attachments
as part of an investigation; inspect them as untrusted data.

## CLI and HTTP Contracts

The bot token (`-t/--token`) is mandatory. Chat context (`-c/--chat_id`) is optional
for bot-only analysis, but required for downloads and invite-link creation.
Both `--downloads` and `--download` are supported.

Only `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from `.env` may influence runtime
configuration. Never add environment-file fallbacks for bot tokens or chat IDs.
Do not silently change the existing token-display policy; never copy real
credentials into tests, documentation, external documentation queries, or commits.

Route Bot API calls through the shared HTTP helpers. Preserve finite connection
and read timeouts, disabled redirects, and explicit HTTP/JSON error handling.
Do not add automatic retries for operations that may already have taken effect.
Do not expose request URLs containing credentials through transport errors.

Validate CLI arguments before network access or output creation. Starting
message IDs must be positive; export limits must be nonnegative, with zero
meaning unlimited. Batch sizes are between 1 and 200, with a default of 50.

Keep `--json` stdout machine-readable. Include report-save errors in the final
stdout report. Preserve exit codes: 0 for no top-level errors, 1 for reported
failures, 2 for invalid arguments, and 130 for interruption. Individual media
failures are recorded separately and do not currently force a nonzero exit.

## Telegram Access and Sessions

Bot authentication is the download default and uses the CLI token. User
authentication is explicit through `--download-auth user`. Keep default session
paths separate: `sessions/<bot_username>_<chat_reference>/bot.session` and
`user.session`. Do not delete or migrate existing sessions without approval.

Pyrofork's `bot_token` applies only to new sessions; it does not replace the
identity of an existing session. Never assume that passing a token reauthenticates
a reused session, especially with a custom `--session-name`.

In automatic mode, bot sessions use `idscan` directly. User sessions try history
and may fall back to ID scan. Match batch responses by message ID, not position;
missing messages must not discard valid messages from the same batch.

Unavailable IDs do not prove deletion. Bot privacy flags, administrator rights,
history visibility for new members, and actual historical access are distinct.
Keep labels faithful to the Bot API; an omitted optional field is not `false`.

## Non-Interference and Evidence Handling

Default preliminary analysis is read-only. Creating an additional invite link
requires `--create-invite-link`; do not create or revoke links implicitly.

ID scan may send a temporary `.` to derive the latest ID only when an explicit
`--download-start-id` is absent. Attempt cleanup immediately. A cleanup API or
transport failure must preserve the known ID and produce a warning, not abort
acquisition or trigger a retry. Failure to obtain the ID remains fatal.

Do not contact real Telegram targets, initiate logins, reuse live sessions, or
send test messages unless the user explicitly authorizes that verification.
Use mocked clients and temporary directories for normal development tests.

Review follow-ups still to implement separately: deduplicating partial history
fallbacks and verifying the identity of reused sessions. Do not describe these
as solved or introduce resume/deduplication between runs without approval.

## Export Contracts

Keep each chat under `downloads/<bot_username>/<chat_id>/`, with sanitized
`messages_<chat_title>.jsonl` and `.txt` filenames. Without a usable title,
fall back to the chat ID. Keep attachment files in that chat's `media/` directory.
Use message-ID-prefixed sanitized filenames to distinguish same-named attachments.
Keep displayed and exported paths relative to the working directory.
Stage TXT and JSONL in a separate `.acquisition-*` directory until acquisition
completes. Preserve previous logs and retain partial new logs on failure or
interruption. Roll back log replacements if publication fails. Never overwrite
existing media during acquisition; add numeric suffixes on filename collisions.

JSONL retains message text and richer investigative metadata. TXT remains a
minimal human-readable log, omitting empty fields. Do not add a separate
acquisition metadata file without a request. Preserve existing JSON field names
unless a schema change is explicitly requested and documented.

Pyrofork 2.3.69 returns naive local message datetimes. Convert them to actual UTC
for JSONL, including the historical daylight-saving offset; never simply attach
UTC to a naive datetime. TXT dates include an explicit local offset. Recheck
this assumption against library source when upgrading Pyrofork.

Download only photos, videos, documents (including archives), audio, voice
messages, and video notes. Stickers, animations/GIFs, link previews, dice, and
other non-allowlisted media are not downloaded or counted as failures. Their
messages remain exportable. `--skip-media-download` disables all attachments.
Create `media/` only when an allowed download is attempted.

SHA-256 hashing is opt-in through `--hash-media`, and belongs in JSONL only.
Hashing failure must not reclassify a successful download as failed. Do not
introduce automatic media retries, default hashing, or content execution.

## Documentation and Dependencies

Use Context7 for Pyrofork, Requests, and Telegram API documentation when available.
Verify method semantics and labels against official documentation, and inspect
the installed source when indexed documentation targets a different version.
Do not send private code, tokens, or evidence to documentation services.

Keep runtime dependencies pinned to tested versions. Do not install upstream
`Pyrogram` alongside `pyrofork`: both use the `pyrogram` namespace. Dependency
changes need their own compatibility checks; new versions are not automatic fixes.

References:

- Telegram Bot API: https://core.telegram.org/bots/api
- Bot privacy behavior: https://core.telegram.org/bots/features#privacy-mode
- Pyrofork client/session options: https://github.com/Mayuri-Chan/pyrofork/blob/main/docs/source/api/client.rst

## Verification and Commits

Add regression tests for fixes and tests for new behavior. Cover failure paths,
not just successful requests. Keep tests offline and independent of credentials,
live sessions, and existing evidence. Use temporary directories for writes.

Run relevant tests during development and the full suite before committing:

```bash
venv/bin/python -m unittest discover -s tests
TZ=Europe/Rome venv/bin/python -m unittest discover -s tests
venv/bin/python -m pip check
git diff --check
```

For timezone changes, cover naive local and timezone-aware values, winter and
summer offsets, and restore any modified process timezone after each test.
Documentation-only changes need a consistency check; do not claim runtime
behavior changed. If verification is blocked, report the limitation honestly.

After each completed and tested change or implementation, create a Git commit.
Every commit must have a concise title and a descriptive body, both in English.
Explain what changed and why. Stage only relevant files, inspect the staged
diff, and preserve unrelated user changes and untracked files. Do not amend
commits or push to a remote unless explicitly requested.
