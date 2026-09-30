# Tosint - Telegram OSINT Tool

Tosint is a Python-based OSINT tool for Telegram investigations.  
It analyzes bot tokens and target chats (channels, groups, and DMs) to quickly extract actionable intelligence.

Built for investigators, threat analysts, and security researchers, Tosint helps profile malicious infrastructure used in phishing, malware operations, credential theft, and related campaigns.

It can also export full chat history and media for forensic collection and offline analysis.

## Use Cases

- Telegram OSINT investigations on suspicious bots/channels/groups/DMs
- Threat intelligence enrichment for phishing and malware delivery chains
- DFIR/forensic collection of Telegram chat metadata and content
- Telegram channel/group message export for offline analysis

## Legal and Ethical Use

Tosint is intended for lawful investigative, research, DFIR, and threat intelligence activities.

You must not use this tool for illegal activities, unauthorized access, or any operation that violates Telegram's Terms of Service or the laws applicable in your jurisdiction.

## Telegram OSINT Data Extracted

### Bot Intelligence

- Bot identity: first name, username, user ID
- Bot capability signal: `can_read_all_group_messages` (true when privacy mode
  is disabled; false does not mean the bot cannot read any group messages)
- Bot profile metadata:
  - `getMyDescription`
  - `getMyShortDescription`
- Bot default requested administrator rights (not actual rights in the target chat):
  - `getMyDefaultAdministratorRights` for groups
  - `getMyDefaultAdministratorRights` for channels
- Bot status in target chat: `getChatMember` (`administrator`, `member`, etc.)
- Webhook infrastructure via `getWebhookInfo`: configured URL, IP address,
  pending updates, delivery errors and other returned settings. An empty URL
  means no webhook is configured; it does not identify the polling server.
- Registered commands via `getMyCommands` (default scope and language only;
  this is not a complete inventory of all commands the bot may support).
- Default menu via `getChatMenuButton`: button type, text and Web App URL when
  available. Chat-specific menu overrides are not queried.

These are read-only API calls. Results are also preserved in JSON under
`bot.webhook`, `bot.commands` and `bot.menu_button`. Failed enrichment calls
are reported without preventing the remaining analysis or requested download.
The group-reading flag describes privacy mode, not guaranteed historical
message access. Optional API fields are omitted from text output when not
returned; their absence must not be interpreted as `false`.

### Chat Intelligence

- Core metadata from `getChat`:
  - title, type, ID
  - username and active usernames
  - description (normalized to a single line)
  - visibility/policy flags (when available), such as:
    - visible history
    - hidden members
    - protected content
    - join-by-request
    - slow mode
    - auto-delete timer
  - linked chat ID
- Linked chat enrichment:
  - if `linked_chat_id` is available, Tosint performs a second `getChat`
- Invite links:
  - existing invite link (if exposed by Telegram)
  - optional additional link via `createChatInviteLink` (`--create-invite-link`)
- Member count: `getChatMemberCount`

### Admin Intelligence

From `getChatAdministrators`, Tosint prints each admin with:

- index (`#1`, `#2`, ...)
- first name / last name
- user ID
- username
- bot flag
- role/status (`creator`, `administrator`, ...)
- custom title (if present)
- granular admin permissions (`can_*`, plus `is_anonymous`)

Tosint requests `return_bots=True` to include other bot administrators alongside
human administrators. This lookup is skipped for private chats.

## Output Formats (Text and JSON)

Tosint supports both human-readable and JSON output.

- Default: formatted text output
- `--json`: JSON only on stdout (no text output)
- `--json-file <path>`: save JSON report to file
- `--json --json-file <path>`: JSON on stdout + JSON saved to file

Message exports use a minimal TXT format and a richer JSONL format. Only JSONL
includes the source `chat_id`, UTC message/edit timestamps, reply message ID,
per-message acquisition timestamp (`acquired_at`), original attachment name,
MIME type, Telegram file size, file identifiers and downloaded file size in
bytes. Unavailable fields are `null`; metadata is retained even when attachment
downloads are skipped. Pyrofork's naive local timestamps are converted to UTC,
including the daylight saving offset applicable to the message date.
TXT message dates use local time with an explicit UTC offset, for example
`2026-09-30T12:40:35+02:00`.

Exports contain only messages Telegram makes available to the authenticated
bot or user session. Deleted or inaccessible messages cannot be guaranteed to
be recovered, and different sessions may have access to different content.
In `idscan` mode, `Message IDs Scanned` counts requested IDs, not existing
messages. `Unavailable Message IDs` counts IDs for which no dated message was
returned; this does not prove deletion. Progress uses `ids_scanned` and
`unavailable_ids`, while history mode counts messages returned by Telegram.
The JSON report retains the `messages_scanned` key for compatibility and adds
`unavailable_message_ids` for the ID-scan count.

SHA-256 hashing is disabled by default. Enable it explicitly with:

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --download --hash-media
```

Hashes appear as `sha256` in JSONL only for downloaded files when requested.
Hashing reads each entire file in chunks and can add time for large downloads.
Hash failures are recorded without treating a successful download as failed.
The TXT format stays minimal, and no separate acquisition file is created.

## Installation

1. Clone the repository:

```bash
git clone https://github.com/drego85/tosint.git
cd tosint
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

`tgcrypto` is optional from a functional perspective, but strongly recommended for much faster MTProto upload/download performance.

## How to Get Telegram API_ID and API_HASH

To use MTProto download features (`--downloads`), you need your Telegram `API_ID` and `API_HASH`.

Follow the official [Telegram guide](https://core.telegram.org/api/obtaining_api_id).

For convenience, you can save these values in a local `.env` file (faster repeated analysis), or skip `.env` and enter them interactively at runtime.

Recommended `.env` format:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
```

## Usage and CLI Examples

### Interactive mode

```bash
python3 tosint.py
```

### CLI mode

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID>
```

### Bot-only preliminary analysis (no chat context)

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN>
```

### JSON only (stdout)

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --json
```

### Create an additional invite link

By default, Tosint only displays the existing invite link returned by `getChat`,
when available. To create an additional link, use:

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --create-invite-link
```

This requires appropriate bot administrator rights. The existing primary link
is not revoked. Telegram does not expose every active invite link through `getChat`.

### Save JSON report to file

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --json-file /tmp/tosint_report.json
```

### Download chat history and media

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --downloads
```

This uses `--download-mode auto` by default:
- with bot authentication (default), directly uses ID scan (`get_messages` by `message_id`).
- with user authentication, first tries MTProto history (`get_chat_history`) and falls back to ID scan if history fails.
- output is saved under `downloads/<bot_username>/<chat_id>/` with:
  - `messages_<chat_title_sanitized>.jsonl` (structured JSON lines)
  - `messages_<chat_title_sanitized>.txt` (human-readable text log)
  - `media/` (downloaded attachments when media download is enabled)

Each chat has a separate export directory, including when the same bot is used
for multiple chats. For chats without a title, filenames use the chat ID, for
example `downloads/chartid_bot/5901023723/messages_5901023723.jsonl`.
Existing exports in the previous directory layout are left unchanged.

ID scan retrieves up to 50 message IDs per request by default. Configure this
with `--download-batch-size <1-200>`. Missing or deleted IDs are skipped without
discarding the other messages in the batch. Exports remain ordered from newest
to oldest; `scanned` counts processed IDs and `exported` counts valid messages.
If the entire request fails, the error is reported rather than silently skipping
the batch. `--download-limit` still limits the number of messages exported.

Attachment downloads include only photos, videos, documents, audio, voice
messages and video notes, based on Telegram's media type. Stickers (including
animated and video stickers), GIFs/animations, link previews, dice and other
media types are excluded from file downloads and do not count as failed
downloads. Their messages are still exported to TXT and JSONL; emoji within
message text are preserved. Use `--skip-media-download` to skip all attachments.

### Download authentication modes (`--download-auth`)

- `bot` (default): uses the bot token provided with `-t/--token` for the download session.
- `user`: forces user authentication and shows Pyrogram login prompt (phone number or QR code flow).

By default, authentication modes use separate session files:

```text
sessions/<bot_username>_<chat_id>/bot.session
sessions/<bot_username>_<chat_id>/user.session
```

Previous `tosint_user.session` files are left unchanged; the first run with the
new paths creates a fresh session. Bot authentication uses the CLI token, while
user authentication requires login. If you override `--session-name`, choose
distinct paths for bot and user authentication to keep their sessions separate.

### Download overwrite modes (`--download-overwrite`)

- `ask` (default): if the target chat's download directory already exists and is not empty, Tosint asks whether to continue.
- `always`: continue without prompting and reuse the existing directory.
- `never`: skip the download when the target directory already exists and is not empty.

Example:

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --downloads --download-overwrite always
```

### Options

- `-t`, `--token`: Telegram bot token (with or without `bot` prefix) **required**
- `-c`, `--chat_id`: Telegram chat ID (e.g. `-100...` for channels/supergroups). Required for chat/admin analysis and `--downloads`
- `--json`: print JSON report only
- `--json-file`: save JSON report to chosen path
- `--create-invite-link`: create an additional invite link (requires `-c` and appropriate bot administrator rights)
- `--downloads` (`--download` alias): download messages/media
- `--api-id`: Telegram API ID (used by `--downloads`)
- `--api-hash`: Telegram API hash (used by `--downloads`)
- `--session-name`: Pyrofork session name/path override. If omitted, Tosint uses `sessions/<bot>_<chat>/bot` or `sessions/<bot>_<chat>/user`, according to `--download-auth`
- `--download-dir`: target folder for downloaded content (default: `downloads`)
- `--download-overwrite`: overwrite policy for an existing non-empty download directory: `ask`, `always`, or `never` (default: `ask`)
- `--download-limit`: max messages to export (`0` = all)
- `--download-mode`: `auto`, `history`, `idscan` (default: `auto`)
- `--download-auth`: `bot`, `user` (default: `bot`)
- `--download-start-id`: start `message_id` for `idscan` mode
- `--download-progress-every`: print progress every N scanned messages (`0` disables, default: `50`)
- `--download-batch-size`: IDs per request in `idscan` mode (`1` to `200`, default: `50`; ignored in `history` mode)
- `--skip-media-download`: skip attachment files and export only message metadata/text
- `--hash-media`: optionally compute SHA-256 for downloaded attachments and record it in JSONL (disabled by default)
- `--env-file`: `.env` path for loading values (default: `.env`)

### Example Text Output (obfuscated)

`Chat History Visible To New Members` describes access for newly joined
members, not guaranteed completeness of the bot's export. A primary invite
link not returned by Telegram does not prove that the chat has no invite links.
Administrator attributes include `is_anonymous` and `can_be_edited`; the latter
indicates whether the querying bot can edit that administrator's privileges.

```text
Analysis of token: 81XXXXXX66:AAF... and chat id: -1003XXXX075

[BOT]
Bot First Name: Example Bot
Bot Username: example_bot
Bot User ID: 81XXXXXX66
Bot Can Read All Group Messages: false
Bot Short Description: @example_channel
Bot Default Requested Administrator Rights (groups/supergroups): {"can_manage_chat": false, ...}
Bot Default Requested Administrator Rights (channels): {"can_manage_chat": false, ...}
Bot Chat Membership Status: administrator

[CHAT]
Chat Title: Example Channel
Chat Type: channel
Chat ID: -1003XXXX075
Chat Username: example_channel
Chat Active Usernames: ["example_channel"]
Chat Description: Example single-line description.
Chat History Visible To New Members: true
Invite Links:
  Primary Chat Invite Link: https://t.me/+XXXXXXXXXXXX
Chat Member Count: 339

[ADMINS]
Administrators in the chat:
- #1
  First Name: Example
  Last Name: Admin
  User ID: 20XXXX39
  Username: ExampleAdmin
  Is Bot: false
  Chat Membership Status: administrator
  Administrator Rights and Attributes: {"can_manage_chat": true, "can_delete_messages": true, ...}
```

### Example JSON Report (structure)

```json
{
  "input": {
    "token": "81XXXXXX66:AAF...",
    "chat_id": "-1003XXXX075"
  },
  "bot": {
    "first_name": "Example Bot",
    "username": "example_bot",
    "user_id": 8100000000,
    "can_read_all_group_messages": false,
    "short_description": "@example_channel",
    "default_admin_rights_groups": {},
    "default_admin_rights_channels": {},
    "status_in_chat": "administrator"
  },
  "chat": {
    "id": -1003000000075,
    "title": "Example Channel",
    "type": "channel",
    "member_count": 339
  },
  "invite_links": {
    "chat_invite_link": "https://t.me/+XXXXXXXXXXXX",
    "created": null
  },
  "admins": [
    {
      "index": 1,
      "first_name": "Example",
      "last_name": "Admin",
      "user_id": 20000039,
      "username": "ExampleAdmin",
      "is_bot": false,
      "status": "administrator",
      "custom_title": null,
      "permissions": {
        "can_manage_chat": true
      }
    }
  ],
  "errors": []
}
```

## Alternatives and Related Projects

- [TelePeek](https://telepeek.com/)
- [TeleTracker](https://github.com/tsale/TeleTracker/)
- [telegram-scraper](https://github.com/unnohwn/telegram-scraper)
- [telegram-scraper DarkWebInformer](https://github.com/DarkWebInformer/telegram-scraper)
- [Matkap](https://github.com/0x6rss/matkap)

## Operational and Forensic Notes

- Some fields are returned by Telegram only when the bot has enough visibility/permissions.
- Invite-link creation is an active operation performed only with `--create-invite-link` and may fail based on bot permissions. The default analysis reads the existing link without creating or revoking links.
- During MTProto downloads in `idscan` mode (or `auto` fallback), Tosint may send a temporary `.` message to derive the latest `message_id` when no explicit `--download-start-id` is provided.
- Tosint then attempts to delete that temporary message immediately. If deletion is not allowed by chat rules/permissions, the message may remain visible and this is reported in the tool output (`Temporary message cleanup failed: ...`).
- OSINT/forensics note: this behavior is an active interaction with the target chat. If strict non-interference is required, provide `--download-start-id` explicitly to avoid sending the temporary message.

## Troubleshooting

- Bot API HTTP calls use a 10-second connection timeout and a 30-second read
  timeout. Network failures, invalid responses, server errors and HTTP 429 rate
  limits are reported explicitly. Requests are not automatically retried; after
  a timeout, an active operation may already have succeeded on Telegram.
- A failed `getMe` with Telegram error code 401 is reported as an invalid or
  revoked token. Other failures are reported with their actual cause.
- CLI exit codes: `0` for completion without top-level report errors, `1` for
  reported failures, `2` for invalid CLI arguments, and `130` for interruption.
  Individual media failures remain available in the download report and counter.

- `SESSION_REVOKED`: in bot authentication mode, Tosint preserves the invalid
  MTProto session as `<session>.session.revoked-<timestamp>` and automatically
  retries once with a fresh session using the supplied bot token. The recovery
  is also recorded in JSON output as `session_recovered` and
  `revoked_session_archive`. User sessions are not replaced automatically
  because they require interactive authentication.
- `PEER_ID_INVALID` / `CHAT_ID_INVALID`: try a separate session (`--session-name`) and/or the other authentication mode (bot token vs user account).
- Many scanned messages but `exported=0`: the scanned ID range may not be accessible/visible for that session; try `--download-mode history` or a different `--download-start-id`.
- Frequent `Waiting for X seconds` messages: this is Telegram FloodWait rate limiting and is expected on large `idscan` runs.

## Contributing and Supporting the Project

There are three ways you can contribute to the development of **Tosint**:

1. **Development Contributions**:

   Please ensure that your code follows best practices and includes relevant tests.

2. **Donation Support**:
   If you find this project useful and would like to support its development, you can also make a donation via [Buy Me a Coffee](https://buymeacoffee.com/andreadraghetti). Your support is greatly appreciated and helps to keep this project going!

   [![Buy Me a Coffee](https://img.shields.io/badge/-Buy%20Me%20a%20Coffee-orange?logo=buy-me-a-coffee&logoColor=white&style=flat-square)](https://buymeacoffee.com/andreadraghetti)

3. **Share the Project**:
   Sharing Tosint with colleagues, friends, and anyone interested in OSINT helps the project grow and reach more practitioners in the community.

## License

This project is licensed under the GNU General Public License v3.0.
