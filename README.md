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

## Telegram OSINT Data Extracted

### Bot Intelligence

- Bot identity: first name, username, user ID
- Bot capability signal: `can_read_all_group_messages`
- Bot profile metadata:
  - `getMyDescription`
  - `getMyShortDescription`
- Bot default privileges:
  - `getMyDefaultAdministratorRights` for groups
  - `getMyDefaultAdministratorRights` for channels
- Bot status in target chat: `getChatMember` (`administrator`, `member`, etc.)

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
  - `exportChatInviteLink`
  - `createChatInviteLink`
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

## Output Formats (Text and JSON)

Tosint supports both human-readable and JSON output.

- Default: formatted text output
- `--json`: JSON only on stdout (no text output)
- `--json-file <path>`: save JSON report to file
- `--json --json-file <path>`: JSON on stdout + JSON saved to file

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

### Save JSON report to file

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --json-file /tmp/tosint_report.json
```

### Download chat history and media

```bash
python3 tosint.py -t <TELEGRAM_BOT_TOKEN> -c <TELEGRAM_CHAT_ID> --downloads
```

This uses `--download-mode auto` by default:
- first tries MTProto history (`get_chat_history`)
- if that fails (for example `PEER_ID_INVALID`), it falls back to ID scan (`get_messages` by `message_id`).
- output is saved under `downloads/<bot_username>/` with:
  - `messages_<chat_title_sanitized>.jsonl` (structured JSON lines)
  - `messages_<chat_title_sanitized>.txt` (human-readable text log)
  - `media/` (downloaded attachments when media download is enabled)

### Download authentication modes (`--download-auth`)

- `bot` (default): uses the bot token provided with `-t/--token` for the download session.
- `user`: forces user authentication and shows Pyrogram login prompt (phone number or QR code flow).


### Options

- `-t`, `--token`: Telegram bot token (with or without `bot` prefix) **required**
- `-c`, `--chat_id`: Telegram chat ID (e.g. `-100...` for channels/supergroups). Required for chat/admin analysis and `--downloads`
- `--json`: print JSON report only
- `--json-file`: save JSON report to chosen path
- `--downloads` (`--download` alias): download messages/media
- `--api-id`: Telegram API ID (used by `--downloads`)
- `--api-hash`: Telegram API hash (used by `--downloads`)
- `--session-name`: Pyrofork session name/path override. If omitted, Tosint auto-creates a scoped session under `sessions/<bot>_<chat>/tosint_user`
- `--download-dir`: target folder for downloaded content (default: `downloads`)
- `--download-limit`: max messages to export (`0` = all)
- `--download-mode`: `auto`, `history`, `idscan` (default: `auto`)
- `--download-auth`: `bot`, `user` (default: `bot`)
- `--download-start-id`: start `message_id` for `idscan` mode
- `--download-progress-every`: print progress every N scanned messages (`0` disables, default: `50`)
- `--skip-media-download`: skip attachment files and export only message metadata/text
- `--env-file`: `.env` path for loading values (default: `.env`)

### Example Text Output (obfuscated)

```text
Analysis of token: 81XXXXXX66:AAF... and chat id: -1003XXXX075

[BOT]
Bot First Name: Example Bot
Bot Username: example_bot
Bot User ID: 81XXXXXX66
Bot Can Read Group Messages: false
Bot Short Description: @example_channel
Bot Default Administrator Rights (groups): {"can_manage_chat": false, ...}
Bot Default Administrator Rights (channels): {"can_manage_chat": false, ...}
Bot In The Chat Is An: administrator

[CHAT]
Chat Title: Example Channel
Chat Type: channel
Chat ID: -1003XXXX075
Chat Username: example_channel
Chat Active Usernames: ["example_channel"]
Chat Description: Example single-line description.
Chat Has Visible History: true
Invite Links:
  Chat Invite Link: https://t.me/+XXXXXXXXXXXX
  Chat Invite Link (exported): https://t.me/+YYYYYYYYYYYY
  Chat Invite Link (created): https://t.me/+ZZZZZZZZZZZZ
Number of users in the chat: 339

[ADMINS]
Administrators in the chat:
- #1
  First Name: Example
  Last Name: Admin
  User ID: 20XXXX39
  Username: ExampleAdmin
  Is Bot: false
  Status: administrator
  Permissions: {"can_manage_chat": true, "can_delete_messages": true, ...}
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
    "exported": "https://t.me/+YYYYYYYYYYYY",
    "created": "https://t.me/+ZZZZZZZZZZZZ"
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

## Operational and Forensic Notes

- Some fields are returned by Telegram only when the bot has enough visibility/permissions.
- Invite-link methods are active operations (`exportChatInviteLink`, `createChatInviteLink`) and may fail based on bot role.
- During MTProto downloads in `idscan` mode (or `auto` fallback), Tosint may send a temporary `.` message to derive the latest `message_id` when no explicit `--download-start-id` is provided.
- Tosint then attempts to delete that temporary message immediately. If deletion is not allowed by chat rules/permissions, the message may remain visible and this is reported in the tool output (`Temporary message cleanup failed: ...`).
- OSINT/forensics note: this behavior is an active interaction with the target chat. If strict non-interference is required, provide `--download-start-id` explicitly to avoid sending the temporary message.

## Troubleshooting

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
