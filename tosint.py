#!/usr/bin/env python3
import os
import json
import requests
import argparse
import mimetypes
import sys
import hashlib
import sqlite3
from contextlib import contextmanager, nullcontext, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

TEXT_OUTPUT_ENABLED = True
HTTP_TIMEOUT = (10, 30)
KURIGRAM_SESSION_VERSION = 7
MEDIA_FILENAME_MAX_BYTES = 255
DOWNLOADABLE_MEDIA_TYPES = frozenset({
    "photo", "video", "document", "audio", "voice", "video_note",
})


class TelegramAPIError(RuntimeError):
    """A Bot API request failed before a usable Telegram response was received."""


class HistoryRetrievalError(RuntimeError):
    """Reading Telegram history failed, independently of writing the export."""


def text_print(*args, **kwargs):
    if TEXT_OUTPUT_ENABLED:
        print(*args, **kwargs)


def format_output_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def print_field(data, key, label=None):
    if key not in data:
        return
    value = data[key]
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    text_print(f"{label or key}: {format_output_value(value)}")


def normalize_single_line(value):
    return " ".join(str(value).split())


def print_section(title):
    text_print(f"\n[{title}]")


def print_chat_summary(chat):
    print_field(chat, "title", "Chat Title")
    print_field(chat, "type", "Chat Type")
    print_field(chat, "id", "Chat ID")
    print_field(chat, "username", "Chat Username")
    print_field(chat, "active_usernames", "Chat Active Usernames")
    if "description" in chat and chat["description"] is not None:
        text_print(f"Chat Description: {normalize_single_line(chat['description'])}")
    print_field(chat, "is_forum", "Chat Is Forum")
    print_field(chat, "is_direct_messages", "Chat Is Channel Direct Messages")
    print_field(chat, "has_visible_history", "Chat History Visible To New Members")
    print_field(chat, "has_hidden_members", "Chat Member List Hidden From Non-Administrators")
    print_field(chat, "has_protected_content", "Chat Has Protected Content")
    print_field(chat, "join_to_send_messages", "Membership Required To Send Messages")
    print_field(chat, "join_by_request", "Direct Join Requires Admin Approval (without invite link)")
    print_field(chat, "slow_mode_delay", "Slow Mode Delay (s)")
    print_field(chat, "message_auto_delete_time", "Message Auto Delete Time (s)")
    print_field(chat, "linked_chat_id", "Linked Chat ID")
    if "location" in chat and chat["location"]:
        text_print(f"Chat Location: {format_output_value(chat['location'])}")

    if "permissions" in chat and chat["permissions"]:
        text_print(f"Default Chat Member Permissions: {format_output_value(chat['permissions'])}")

    if "pinned_message" in chat and chat["pinned_message"]:
        pinned = chat["pinned_message"]
        text_print("Most Recent Pinned Message (by send date):")
        print_field(pinned, "message_id", "  Message ID")
        print_field(pinned, "date", "  Sent Date (Unix timestamp)")
        print_field(pinned, "author_signature", "  Author Signature")
        print_field(pinned, "text", "  Text")
        if "from" in pinned and pinned["from"]:
            text_print(f"  Sender User: {format_output_value(pinned['from'])}")
        if "sender_chat" in pinned and pinned["sender_chat"]:
            text_print(f"  Sender Chat: {pinned['sender_chat']}")


def print_linked_chat_summary(chat):
    text_print("Linked Chat Details:")
    print_field(chat, "title", "  Title")
    print_field(chat, "type", "  Type")
    print_field(chat, "id", "  ID")
    print_field(chat, "username", "  Username")
    print_field(chat, "active_usernames", "  Active Usernames")
    if "description" in chat and chat["description"] is not None:
        text_print(f"  Description: {normalize_single_line(chat['description'])}")


def format_admin_name(user):
    if not user:
        return "Unknown"
    first_name = user.get("first_name", "")
    last_name = user.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name
    if user.get("username"):
        return user["username"]
    return str(user.get("id", "Unknown"))


def extract_admin_permissions(chat_member):
    permissions = {}
    for key, value in chat_member.items():
        if key.startswith("can_") and isinstance(value, bool):
            permissions[key] = value
    for key in ["is_anonymous", "can_manage_direct_messages"]:
        if key in chat_member and isinstance(chat_member[key], bool):
            permissions[key] = chat_member[key]
    return permissions


def print_admin_details(chat_member, index):
    user = chat_member.get("user", {})
    text_print(f"- #{index}")
    print_field(user, "first_name", "  First Name")
    print_field(user, "last_name", "  Last Name")
    print_field(user, "id", "  User ID")
    print_field(user, "username", "  Username")
    print_field(user, "is_bot", "  Is Bot")
    print_field(chat_member, "status", "  Chat Membership Status")
    print_field(chat_member, "custom_title", "  Custom Title")
    permissions = extract_admin_permissions(chat_member)
    if permissions:
        text_print(f"  Administrator Rights and Attributes: {format_output_value(permissions)}")


def telegram_api_request(token, method, http_method="GET", params=None, data=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = requests.request(http_method, url, params=params, data=data,
                                    timeout=HTTP_TIMEOUT, allow_redirects=False)
    except requests.Timeout:
        raise TelegramAPIError(f"{method}: request timed out (connection: 10s, read: 30s).") from None
    except requests.RequestException:
        # Requests exceptions can include the URL, which contains the bot token.
        raise TelegramAPIError(f"{method}: connection or transport error contacting Telegram.") from None

    if response.status_code == 429:
        try:
            retry_after = response.json().get("parameters", {}).get("retry_after")
        except (ValueError, AttributeError, TypeError):
            retry_after = None
        wait_info = f" Retry after {retry_after} seconds." if isinstance(retry_after, int) else ""
        raise TelegramAPIError(f"{method}: Telegram rate limit exceeded (HTTP 429).{wait_info}")
    if response.status_code >= 500:
        raise TelegramAPIError(f"{method}: Telegram server error (HTTP {response.status_code}).")

    try:
        payload = response.json()
    except ValueError:
        raise TelegramAPIError(f"{method}: invalid JSON response (HTTP {response.status_code}).") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        raise TelegramAPIError(f"{method}: unexpected Telegram response (HTTP {response.status_code}).")
    if not 200 <= response.status_code < 300 and payload["ok"]:
        raise TelegramAPIError(f"{method}: unexpected HTTP status {response.status_code}.")
    if payload["ok"] and "result" not in payload:
        raise TelegramAPIError(f"{method}: Telegram response is missing its result.")
    if not payload["ok"] and not isinstance(payload.get("description"), str):
        raise TelegramAPIError(f"{method}: Telegram error response is missing its description.")
    return payload


def telegram_api_get(token, method, params=None):
    return telegram_api_request(token, method, params=params)


def telegram_api_post(token, method, data=None):
    return telegram_api_request(token, method, http_method="POST", data=data)


def get_bot_info(token):
    return telegram_api_get(token, "getMe")


def get_bot_description(token):
    return telegram_api_get(token, "getMyDescription")


def get_bot_short_description(token):
    return telegram_api_get(token, "getMyShortDescription")


def get_webhook_info(token):
    return telegram_api_get(token, "getWebhookInfo")


def get_bot_commands(token):
    return telegram_api_get(token, "getMyCommands")


def get_bot_menu_button(token):
    return telegram_api_get(token, "getChatMenuButton")


def enrich_bot_info(token, report):
    for method, fetch, key, expected_type in (
        ("getWebhookInfo", get_webhook_info, "webhook", dict),
        ("getMyCommands", get_bot_commands, "commands", list),
        ("getChatMenuButton", get_bot_menu_button, "menu_button", dict),
    ):
        try:
            response = fetch(token)
            if not response.get("ok"):
                raise TelegramAPIError(f"{method}: {response.get('description', 'Unknown Telegram API error')}")
            value = response.get("result")
            if not isinstance(value, expected_type):
                raise TelegramAPIError(f"{method}: unexpected result format.")
        except TelegramAPIError as error:
            report["errors"].append(str(error))
            text_print(f"ATTENTION {error}")
            continue
        report["bot"][key] = value
        if key == "webhook":
            if not value.get("url"):
                text_print("Bot Webhook: Not configured")
            for field, label in (
                ("url", "Bot Webhook URL"),
                ("ip_address", "Bot Webhook IP Address"),
                ("pending_update_count", "Bot Pending Updates Awaiting Delivery"),
                ("has_custom_certificate", "Bot Webhook Has Custom Certificate"),
                ("last_error_date", "Bot Webhook Last Delivery Error Date (Unix timestamp)"),
                ("last_error_message", "Bot Webhook Last Delivery Error"),
                ("last_synchronization_error_date", "Bot Last Update Synchronization Error Date (Unix timestamp)"),
                ("max_connections", "Bot Webhook Max Simultaneous HTTPS Connections"),
                ("allowed_updates", "Bot Subscribed Update Types"),
            ):
                print_field(value, field, label)
        elif key == "commands":
            text_print("Bot Commands (default scope/language):" if value else "Bot Commands (default scope/language): None")
            for command in value:
                text_print(f"  /{command['command']}: {normalize_single_line(command['description'])}")
        else:
            print_field(value, "type", "Bot Default Menu Button Type")
            print_field(value, "text", "Bot Default Menu Button Text")
            if isinstance(value.get("web_app"), dict):
                print_field(value["web_app"], "url", "Bot Default Menu Button Web App URL")


def get_default_admin_rights(token, for_channels=False):
    params = {"for_channels": "true"} if for_channels else None
    return telegram_api_get(token, "getMyDefaultAdministratorRights", params=params)


def get_bot_chat_member(token, chat_id, user_id):
    params = {"chat_id": chat_id, "user_id": user_id}
    return telegram_api_get(token, "getChatMember", params=params)


def get_chat_info(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "getChat", params=params)


def create_chat_invite_link(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "createChatInviteLink", params=params)


def get_chat_member_count(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "getChatMemberCount", params=params)


def get_chat_administrators(token, chat_id):
    params = {"chat_id": chat_id, "return_bots": "true"}
    return telegram_api_get(token, "getChatAdministrators", params=params)


def send_message(token, chat_id, text):
    data = {"chat_id": chat_id, "text": text}
    return telegram_api_post(token, "sendMessage", data=data)


def delete_message(token, chat_id, message_id):
    data = {"chat_id": chat_id, "message_id": message_id}
    return telegram_api_post(token, "deleteMessage", data=data)


def print_invite_links(chat_invite_link, created_invite_link):
    if not chat_invite_link and not created_invite_link:
        text_print("Invite Links: Not returned by Telegram")
        return
    text_print("Invite Links:")
    if chat_invite_link:
        text_print(f"  Primary Chat Invite Link: {chat_invite_link}")
    if created_invite_link:
        text_print(f"  Additional Chat Invite Link (created): {created_invite_link}")


def build_admin_json(chat_member, index):
    user = chat_member.get("user", {})
    return {
        "index": index,
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "user_id": user.get("id"),
        "username": user.get("username"),
        "is_bot": user.get("is_bot"),
        "status": chat_member.get("status"),
        "custom_title": chat_member.get("custom_title"),
        "permissions": extract_admin_permissions(chat_member),
    }


def emit_json_report(report, print_json, json_file):
    if not print_json and not json_file:
        return
    if json_file:
        try:
            with open(json_file, "w", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(report, indent=2, ensure_ascii=False))
                file_obj.write("\n")
            text_print(f"\nJSON report saved to: {json_file}")
        except OSError as error:
            report["errors"].append("Unable to save JSON report.")
            text_print(f"\nATTENTION Unable to save JSON report to '{json_file}': {error}")
    if print_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))


def load_env_file(env_path):
    env_values = {}
    if not env_path:
        return env_values
    if not os.path.exists(env_path):
        return env_values

    try:
        with open(env_path, "r", encoding="utf-8") as file_obj:
            for raw_line in file_obj:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                if key:
                    env_values[key] = value
    except OSError as error:
        text_print(f"ATTENTION Unable to read env file '{env_path}': {error}")
    return env_values


def prompt_input(prompt):
    if not TEXT_OUTPUT_ENABLED:
        print(prompt, end="", file=sys.stderr, flush=True)
        return input()
    return input(prompt)


def get_value(cli_value, env_values, env_key=None, prompt_text=None):
    if cli_value is not None and str(cli_value).strip():
        return str(cli_value).strip()
    if env_key and env_values.get(env_key):
        return env_values[env_key].strip()
    if prompt_text:
        try:
            return prompt_input(prompt_text).strip()
        except EOFError:
            return None
    return None


def format_utc_datetime(value):
    if isinstance(value, datetime):
        # Kurigram uses local naive datetimes; astimezone applies the local
        # offset for the message date, including daylight saving time.
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def hash_file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def message_to_json(message, downloaded_file=None, chat_id=None, file_metadata=None):
    from_user = getattr(message, "from_user", None)
    sender_chat = getattr(message, "sender_chat", None)
    date_value = format_utc_datetime(getattr(message, "date", None))
    media_type = None
    if getattr(message, "media", None):
        media_type = str(message.media)

    if downloaded_file:
        downloaded_file = display_path(downloaded_file)

    chat = getattr(message, "chat", None)
    media = getattr(message, "media", None)
    media_attr = str(getattr(media, "value", media) or "").rsplit(".", 1)[-1].lower()
    attachment = getattr(message, media_attr, None) if media_attr in DOWNLOADABLE_MEDIA_TYPES else None
    payload = {
        "chat_id": getattr(chat, "id", None),
        "message_id": getattr(message, "id", None),
        "date": date_value,
        "edit_date": format_utc_datetime(getattr(message, "edit_date", None)),
        "reply_to_message_id": getattr(message, "reply_to_message_id", None),
        "acquired_at": format_utc_datetime(datetime.now(timezone.utc)),
        "from_user_id": getattr(from_user, "id", None) if from_user else None,
        "from_username": getattr(from_user, "username", None) if from_user else None,
        "sender_chat_id": getattr(sender_chat, "id", None) if sender_chat else None,
        "text": getattr(message, "text", None),
        "caption": getattr(message, "caption", None),
        "media_type": media_type,
        "downloaded_file": downloaded_file,
        "original_file_name": getattr(attachment, "file_name", None),
        "mime_type": getattr(attachment, "mime_type", None),
        "telegram_file_size": getattr(attachment, "file_size", None),
        "file_id": getattr(attachment, "file_id", None),
        "file_unique_id": getattr(attachment, "file_unique_id", None),
        "downloaded_file_size": None,
    }
    if file_metadata:
        payload.update(file_metadata)
    return payload


def message_to_text(message, downloaded_file=None):
    date_value = getattr(message, "date", None)
    if isinstance(date_value, datetime):
        date_value = date_value.astimezone().isoformat()
    from_user = getattr(message, "from_user", None)
    sender_chat = getattr(message, "sender_chat", None)
    media_type = str(getattr(message, "media", "")) if getattr(message, "media", None) else ""
    text_value = getattr(message, "text", None) or ""
    caption_value = getattr(message, "caption", None) or ""
    if downloaded_file:
        downloaded_file = display_path(downloaded_file)

    lines = []
    message_id = getattr(message, "id", None)
    if message_id is not None:
        lines.append(f"Message ID: {message_id}")
    if date_value:
        lines.append(f"Date: {date_value}")
    if from_user and getattr(from_user, "id", None) is not None:
        lines.append(f"From User ID: {from_user.id}")
    if from_user and getattr(from_user, "username", None):
        lines.append(f"From Username: {from_user.username}")
    if sender_chat and getattr(sender_chat, "id", None) is not None:
        lines.append(f"Sender Chat ID: {sender_chat.id}")
    if media_type:
        lines.append(f"Media Type: {media_type}")
    if text_value:
        lines.append(f"Text: {normalize_single_line(text_value)}")
    if caption_value:
        lines.append(f"Caption: {normalize_single_line(caption_value)}")
    if downloaded_file:
        lines.append(f"Downloaded File: {downloaded_file}")
    return "\n".join(lines) + "\n" + ("-" * 40) + "\n"


def sanitize_path_segment(value):
    if value is None:
        return "unknown"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(value).strip())
    return safe or "unknown"


def build_messages_stem(chat_title=None, chat_id=None):
    title_segment = sanitize_path_segment(chat_title).strip("._-").lower() if chat_title else ""
    if title_segment and title_segment != "unknown":
        return f"messages_{title_segment}"
    chat_segment = sanitize_path_segment(chat_id).strip("._-").lower() if chat_id is not None else ""
    if chat_segment and chat_segment != "unknown":
        return f"messages_{chat_segment}"
    return "messages_unknown"


def build_daily_messages_stem(chat_title=None, chat_id=None, export_date=None):
    day = export_date or datetime.now().date()
    return f"{day.strftime('%Y.%m.%d')}_{build_messages_stem(chat_title, chat_id)}"


def build_bot_download_dir(base_download_dir, bot_username, chat_id):
    bot_segment = sanitize_path_segment(bot_username or "unknown_bot")
    chat_segment = sanitize_path_segment(chat_id).strip(".") or "unknown"
    return os.path.join(base_download_dir, bot_segment, chat_segment)


def build_scoped_session_name(cli_session_name, chat_id, bot_username=None, download_auth_mode="bot"):
    if cli_session_name:
        return cli_session_name
    chat_segment = sanitize_path_segment(chat_id)
    bot_segment = sanitize_path_segment(bot_username) if bot_username else "unknown_bot"
    return os.path.join("sessions", "kurigram", f"{bot_segment}_{chat_segment}", download_auth_mode)


def check_session_format(session_name):
    session_path = Path(f"{session_name}.session")
    if not session_path.is_file():
        return
    try:
        connection = sqlite3.connect(session_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            version = connection.execute("SELECT number FROM version").fetchone()
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
            usernames = {row[1] for row in connection.execute("PRAGMA table_info(usernames)")}
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise RuntimeError(
            f"Unable to inspect saved session {display_path(str(session_path))}: {error}"
        ) from None
    required = {"dc_id", "api_id", "auth_key", "user_id", "is_bot", "server_address", "port"}
    if version != (KURIGRAM_SESSION_VERSION,) or not required <= columns or not {"id", "username"} <= usernames:
        raise RuntimeError(
            f"Incompatible saved session format: {display_path(str(session_path))}. "
            "Use a new --session-name for Kurigram. Legacy Pyrofork sessions "
            "are not converted or replaced."
        )


def should_confirm_overwrite(download_dir, output_stem):
    return any(os.path.exists(os.path.join(download_dir, f"{output_stem}.{extension}"))
               for extension in ("jsonl", "txt"))


def confirm_export_overwrite():
    prompt = "Do you want to overwrite today's exported files? (y/N): "
    try:
        return prompt_input(prompt).strip().lower() == "y"
    except EOFError:
        return False


def display_path(path_value):
    try:
        return os.path.relpath(path_value, os.getcwd())
    except ValueError:
        return path_value


def ensure_dir_path(path_value):
    if path_value.endswith(os.sep):
        return path_value
    return path_value + os.sep


@contextmanager
def open_message_export(download_dir, output_stem, result):
    manifest_path = os.path.join(download_dir, f"{output_stem}.jsonl")
    text_path = os.path.join(download_dir, f"{output_stem}.txt")
    result["manifest_path"] = display_path(manifest_path)
    result["text_path"] = display_path(text_path)
    with open(manifest_path, "w", encoding="utf-8") as manifest_file, open(
        text_path, "w", encoding="utf-8"
    ) as text_file:
        yield manifest_file, text_file


def archive_revoked_session(session_path):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = f"{session_path}.revoked-{timestamp}"
    suffix = 1
    while os.path.exists(archive_path):
        archive_path = f"{session_path}.revoked-{timestamp}-{suffix}"
        suffix += 1
    os.replace(session_path, archive_path)
    for sqlite_suffix in ("-journal", "-wal", "-shm"):
        sidecar_path = f"{session_path}{sqlite_suffix}"
        if os.path.exists(sidecar_path):
            os.replace(sidecar_path, f"{archive_path}{sqlite_suffix}")
    return archive_path


@contextmanager
def open_download_client(
    client_class,
    session_revoked_error,
    session_name,
    client_kwargs,
    recover_revoked_session=False,
    recovery_info=None
):
    recovery_info = recovery_info if recovery_info is not None else {}
    app = client_class(session_name, **client_kwargs)

    try:
        app.start()
    except session_revoked_error:
        if not recover_revoked_session:
            raise

        session_path = str(getattr(app.storage, "database", f"{session_name}.session"))
        if not os.path.isfile(session_path):
            raise RuntimeError(
                f"Telegram session was revoked, but its local file was not found: {session_path}"
            )

        archive_path = archive_revoked_session(session_path)
        recovery_info["session_recovered"] = True
        recovery_info["revoked_session_archive"] = display_path(archive_path)
        text_print("ATTENTION Saved Telegram session was revoked or is no longer valid.")
        text_print(f"Archived revoked session: {display_path(archive_path)}")
        text_print("Retrying once with a new bot session...")

        app = client_class(session_name, **client_kwargs)
        app.start()

    try:
        yield app
    finally:
        app.stop()


def verify_download_identity(app, auth_mode, expected_bot_id=None):
    # Client.start() populates me from Telegram, including for saved sessions.
    identity = app.me
    identity_id = getattr(identity, "id", None)
    is_bot = getattr(identity, "is_bot", None)
    if type(identity_id) is not int or identity_id <= 0 or not isinstance(is_bot, bool):
        raise RuntimeError("Unable to verify the authenticated download session identity.")
    if auth_mode == "bot" and (not is_bot or identity_id != expected_bot_id):
        kind = "bot" if is_bot else "user"
        raise RuntimeError(
            f"Session identity mismatch: expected bot ID {expected_bot_id}, "
            f"found {kind} ID {identity_id}. Use a different --session-name. "
            "The existing session has not been replaced."
        )
    if auth_mode == "user" and is_bot:
        raise RuntimeError(
            f"Session identity mismatch: --download-auth user requires a user "
            f"account, but this session belongs to bot ID {identity_id}. "
            "Use a different --session-name or select --download-auth bot. "
            "The existing session has not been replaced."
        )
    return identity


def infer_media_extension(message):
    # Prefer original file extension when Telegram provides a file name.
    for attr in ("document", "audio", "video", "animation"):
        media_obj = getattr(message, attr, None)
        if media_obj and getattr(media_obj, "file_name", None):
            _, ext = os.path.splitext(media_obj.file_name)
            if ext:
                return ext
        if media_obj and getattr(media_obj, "mime_type", None):
            guessed = mimetypes.guess_extension(media_obj.mime_type)
            if guessed:
                return guessed

    media_type = str(getattr(message, "media", "")).upper()
    if "PHOTO" in media_type:
        return ".jpg"
    if "VOICE" in media_type:
        return ".ogg"
    if "VIDEO_NOTE" in media_type or "VIDEO" in media_type:
        return ".mp4"
    if "STICKER" in media_type:
        return ".webp"
    return None


def infer_media_filename(message):
    for attr in ("document", "audio", "video", "animation"):
        media_obj = getattr(message, attr, None)
        if media_obj and getattr(media_obj, "file_name", None):
            return media_obj.file_name

    inferred_ext = infer_media_extension(message) or ""
    return f"media{inferred_ext}"


def truncate_filename_part(value, byte_limit):
    characters = []
    used = 0
    for character in value:
        size = len(os.fsencode(character))
        if used + size > byte_limit:
            break
        characters.append(character)
        used += size
    return "".join(characters)


def media_filename_limit(media_dir):
    try:
        limit = os.pathconf(media_dir, "PC_NAME_MAX")
        if limit > 0:
            return min(limit, MEDIA_FILENAME_MAX_BYTES)
    except (AttributeError, OSError, ValueError):
        pass
    return MEDIA_FILENAME_MAX_BYTES


def build_unique_media_target(message, media_dir):
    original_name = infer_media_filename(message)
    base_name = sanitize_path_segment(original_name)
    stem, ext = os.path.splitext(base_name)
    if not ext:
        ext = infer_media_extension(message) or ""
    message_id = getattr(message, "id", "unknown")
    prefix = f"{message_id}_"
    limit = media_filename_limit(media_dir)
    suffix = 0
    while True:
        collision_suffix = f"_{suffix}" if suffix else ""
        # Kurigram writes <filename>.temp before moving it to the final path.
        available = limit - len(os.fsencode(prefix + collision_suffix + ".temp"))
        if available < 1:
            raise ValueError("Filesystem filename limit is too small for the media message ID.")
        local_ext = truncate_filename_part(ext, available - 1)
        local_stem = truncate_filename_part(stem or "media", available - len(os.fsencode(local_ext))) or "m"
        candidate = os.path.join(media_dir, f"{prefix}{local_stem}{collision_suffix}{local_ext}")
        if not os.path.exists(candidate) and not os.path.exists(f"{candidate}.temp"):
            return candidate
        suffix += 1


def normalize_downloaded_media_path(downloaded_file, message):
    if not downloaded_file:
        return downloaded_file
    root, ext = os.path.splitext(downloaded_file)
    if ext:
        return downloaded_file

    inferred_ext = infer_media_extension(message)
    if not inferred_ext:
        return downloaded_file

    target_path = f"{downloaded_file}{inferred_ext}"
    try:
        os.replace(downloaded_file, target_path)
        return target_path
    except OSError:
        return downloaded_file


def media_reuse_key(media_type, file_unique_id, file_size):
    kind = str(getattr(media_type, "value", media_type) or "").rsplit(".", 1)[-1].lower()
    if kind not in DOWNLOADABLE_MEDIA_TYPES or not isinstance(file_unique_id, str) or not file_unique_id:
        return None
    if type(file_size) is not int or file_size < 0:
        return None
    return kind, file_unique_id, file_size


def validated_local_media(download_dir, path, expected_size):
    if not isinstance(path, str) or not path:
        return None
    try:
        root = os.path.realpath(download_dir)
        media_dir = os.path.realpath(os.path.join(download_dir, "media"))
        candidate = os.path.realpath(path)
        if os.path.commonpath([root, media_dir]) != root:
            return None
        if os.path.commonpath([media_dir, candidate]) != media_dir:
            return None
        if os.path.isfile(candidate) and os.path.getsize(candidate) == expected_size:
            return os.path.abspath(path)
    except (OSError, ValueError):
        pass
    return None


def load_media_reuse_index(download_dir, chat_id, errors):
    index = {}
    try:
        with os.scandir(download_dir) as entries:
            manifests = sorted(entry.path for entry in entries
                               if entry.is_file() and "messages_" in entry.name
                               and entry.name.endswith(".jsonl"))
    except OSError:
        errors.append("Unable to list previous exports for media reuse.")
        return index
    for manifest in manifests:
        try:
            with open(manifest, encoding="utf-8") as source:
                for line in source:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    if normalize_chat_reference(record.get("chat_id")) != normalize_chat_reference(chat_id):
                        continue
                    size = record.get("downloaded_file_size")
                    key = media_reuse_key(record.get("media_type"), record.get("file_unique_id"), size)
                    if key is None or record.get("telegram_file_size") != size:
                        continue
                    path = validated_local_media(download_dir, record.get("downloaded_file"), size)
                    if path:
                        index.setdefault(key, set()).add(path)
        except (OSError, UnicodeError):
            errors.append(f"Unable to read media references from {display_path(manifest)}.")
    return index


def message_matches_chat(message, chat_id):
    actual_id = getattr(getattr(message, "chat", None), "id", None)
    target_id = normalize_chat_reference(chat_id)
    return type(actual_id) is int and type(target_id) is int and actual_id == target_id


def record_recipient(message, bot_id, recipients, seen):
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    chat_type = getattr(chat, "type", None)
    chat_type = getattr(chat_type, "value", chat_type)
    sender_id = getattr(getattr(message, "from_user", None), "id", None)
    message_id = getattr(message, "id", None)
    date = getattr(message, "date", None)
    if (type(chat_id) is not int or chat_id <= 0 or chat_id == bot_id
            or chat_type not in ("private", "bot")
            or type(sender_id) is not int or sender_id != bot_id
            or getattr(message, "outgoing", None) is not True
            or type(message_id) is not int or message_id <= 0
            or not isinstance(date, datetime)):
        return
    key = (chat_id, message_id)
    if key in seen:
        return
    seen.add(key)
    utc_date = date.astimezone(timezone.utc)
    formatted_date = format_utc_datetime(utc_date)
    row = recipients.setdefault(chat_id, {
        "chat_id": chat_id, "messages_observed": 0,
        "first_message_date": formatted_date, "last_message_date": formatted_date,
    })
    row["messages_observed"] += 1
    if utc_date < datetime.fromisoformat(row["first_message_date"].replace("Z", "+00:00")):
        row["first_message_date"] = formatted_date
    if utc_date > datetime.fromisoformat(row["last_message_date"].replace("Z", "+00:00")):
        row["last_message_date"] = formatted_date


def record_filtered_message_scope(message, chat_id, result):
    diagnostics = result.get("scope_diagnostics")
    if diagnostics is None:
        return

    def integer_or_none(value):
        return value if type(value) is int else None

    actual_id = integer_or_none(getattr(getattr(message, "chat", None), "id", None))
    if actual_id is None:
        reason = "unknown_chat"
    elif actual_id == result.get("authenticated_user_id"):
        reason = "authenticated_peer"
    else:
        reason = "different_chat"
    diagnostics["counts"][reason] += 1
    if len(diagnostics["samples"]) >= 10:
        return
    outgoing = getattr(message, "outgoing", None)
    sample = {
        "reason": reason,
        "message_id": integer_or_none(getattr(message, "id", None)),
        "requested_chat_id": integer_or_none(normalize_chat_reference(chat_id)),
        "parsed_chat_id": actual_id,
        "from_user_id": integer_or_none(getattr(getattr(message, "from_user", None), "id", None)),
        "sender_chat_id": integer_or_none(getattr(getattr(message, "sender_chat", None), "id", None)),
        "outgoing": outgoing if type(outgoing) is bool else None,
        "authenticated_user_id": integer_or_none(result.get("authenticated_user_id")),
    }
    diagnostics["samples"].append(sample)
    text_print("[DOWNLOAD] Scope sample: " + json.dumps(sample))


def process_download_message(message, app, chat_id, download_dir, manifest_file, text_file, result, skip_media=False, hash_media=False, media_index=None):
    if not getattr(message, "date", None):
        return False
    if not message_matches_chat(message, chat_id):
        result["messages_filtered"] = result.get("messages_filtered", 0) + 1
        record_filtered_message_scope(message, chat_id, result)
        return False

    downloaded_file = None
    media_type = getattr(message, "media", None)
    media_type_value = str(getattr(media_type, "value", media_type) or "").rsplit(".", 1)[-1].lower()
    attachment = getattr(message, media_type_value, None) if media_type_value in DOWNLOADABLE_MEDIA_TYPES else None
    reuse_key = media_reuse_key(media_type, getattr(attachment, "file_unique_id", None),
                                getattr(attachment, "file_size", None))

    if not skip_media and media_type_value in DOWNLOADABLE_MEDIA_TYPES:
        try:
            if media_index is not None and reuse_key is not None:
                for path in sorted(media_index.get(reuse_key, ())):
                    downloaded_file = validated_local_media(download_dir, path, reuse_key[2])
                    if downloaded_file:
                        result["media_reused"] = result.get("media_reused", 0) + 1
                        break
            if not downloaded_file:
                media_dir = os.path.join(download_dir, "media")
                os.makedirs(media_dir, exist_ok=True)
                target_file = build_unique_media_target(message, media_dir)
                downloaded_file = app.download_media(message, file_name=target_file)
                downloaded_file = normalize_downloaded_media_path(downloaded_file, message)
                if downloaded_file:
                    result["media_downloaded"] += 1
            if not downloaded_file:
                result["media_failed"] += 1
                result["errors"].append(
                    f"message_id={getattr(message, 'id', None)} download returned no file path"
                )
        except Exception as download_error:
            result["media_failed"] += 1
            result["errors"].append(
                f"message_id={getattr(message, 'id', None)} download error: {download_error}"
            )

    file_metadata = {}
    if downloaded_file:
        try:
            file_metadata["downloaded_file_size"] = os.path.getsize(downloaded_file)
            if media_index is not None and reuse_key is not None:
                path = validated_local_media(download_dir, downloaded_file, reuse_key[2])
                if path:
                    media_index.setdefault(reuse_key, set()).add(path)
        except OSError as error:
            result["errors"].append(f"message_id={message.id} file metadata error: {error}")
        if hash_media:
            try:
                file_metadata["sha256"] = hash_file_sha256(downloaded_file)
            except OSError as error:
                file_metadata["sha256"] = None
                file_metadata["hash_error"] = str(error)
                result["errors"].append(f"message_id={message.id} SHA-256 error: {error}")
    message_payload = message_to_json(message, downloaded_file=downloaded_file, chat_id=chat_id, file_metadata=file_metadata)
    manifest_file.write(json.dumps(message_payload, ensure_ascii=False))
    manifest_file.write("\n")
    text_file.write(message_to_text(message, downloaded_file=downloaded_file))
    result["messages_exported"] += 1
    return True


def normalize_chat_reference(chat_id):
    if chat_id is None:
        return chat_id
    chat_text = str(chat_id).strip()
    if chat_text.startswith("@"):
        return chat_text
    if chat_text.lstrip("-").isdigit():
        return int(chat_text)
    return chat_text


def resolve_start_message_id_with_bot(bot_token, chat_id):
    send_response = send_message(bot_token, chat_id, ".")
    if not send_response.get("ok"):
        raise RuntimeError(
            f"Unable to derive start message id via bot: {send_response.get('description', 'unknown error')}"
        )

    message_id = send_response.get("result", {}).get("message_id")
    if not message_id:
        raise RuntimeError("Unable to derive start message id via bot: missing message_id in response.")

    try:
        delete_response = delete_message(bot_token, chat_id, message_id)
    except TelegramAPIError as error:
        return message_id, f"Temporary message cleanup failed: {error}"
    if not delete_response.get("ok"):
        delete_error = delete_response.get("description", "unknown error")
        # Non-fatal: we still got the message_id and can continue the download.
        return message_id, f"Temporary message cleanup failed: {delete_error}"
    return message_id, None


def download_chat_content(
    chat_id,
    api_id,
    api_hash,
    session_name,
    download_dir,
    history_limit,
    download_mode="auto",
    start_message_id=None,
    bot_token_for_start=None,
    bot_token_for_auth=None,
    download_auth_mode="bot",
    progress_every=50,
    skip_media=False,
    output_stem=None,
    batch_size=50,
    hash_media=False,
    expected_bot_id=None,
    debug_scope=False,
    map_recipients=False,
    download_scope=None,
    overwrite_policy="ask",
    download_report=None
):
    if not 1 <= batch_size <= 200:
        raise ValueError("Download batch size must be between 1 and 200.")
    if start_message_id is not None and start_message_id <= 0:
        raise ValueError("Download start message ID must be greater than zero.")
    if history_limit < 0:
        raise ValueError("Download limit must be zero or greater.")
    acquisition_date = datetime.now().date()
    if download_auth_mode not in ("bot", "user"):
        raise ValueError("Download authentication mode must be bot or user.")
    download_scope = download_scope or ("token" if download_auth_mode == "bot" else "chatid")
    if download_scope not in ("token", "chatid"):
        raise ValueError("Download scope must be token or chatid.")
    if download_scope == "token" and download_auth_mode != "bot":
        raise ValueError("Token download scope requires bot authentication.")
    if overwrite_policy not in ("ask", "always", "never"):
        raise ValueError("Download overwrite policy must be ask, always, or never.")
    if map_recipients and download_auth_mode != "bot":
        raise ValueError("Recipient mapping requires bot authentication.")
    if download_auth_mode == "bot":
        if not bot_token_for_auth:
            raise RuntimeError("download auth mode 'bot' requires a valid bot token.")
        if expected_bot_id is None:
            token_id = bot_token_for_auth.removeprefix("bot").split(":", 1)[0]
            if not token_id.isdigit() or int(token_id) <= 0:
                raise ValueError("Unable to determine the expected bot ID from the token.")
            expected_bot_id = int(token_id)
    try:
        from pyrogram import Client
        from pyrogram.errors import SessionRevoked
    except ImportError as error:
        raise RuntimeError(
            "Kurigram is not installed. Run: python -m pip install -r requirements.txt"
        ) from error

    check_session_format(session_name)
    session_dir = os.path.dirname(session_name)
    if session_dir:
        os.makedirs(session_dir, exist_ok=True)
    result = {
        "chat_id": str(chat_id),
        "session_name": session_name,
        "download_dir": display_path(download_dir),
        "download_root": display_path(os.path.dirname(os.path.abspath(download_dir))) if download_scope == "token" else display_path(download_dir),
        "history_limit": history_limit,
        "batch_size": batch_size,
        "hash_media": hash_media,
        "download_mode_requested": download_mode,
        "download_mode_used": None,
        "download_scope": download_scope,
        "start_message_id": start_message_id,
        "chat_title": None,
        "chat_type": None,
        "messages_scanned": 0,
        "unavailable_message_ids": 0,
        "messages_exported": 0,
        "messages_filtered": 0,
        "messages_skipped_overwrite": 0,
        "skipped_chats": [],
        "chat_exports": [],
        "media_downloaded": 0,
        "media_reused": 0,
        "media_failed": 0,
        "interrupted": False,
        "failed": False,
        "session_recovered": False,
        "revoked_session_archive": None,
        "authenticated_user_id": None,
        "authenticated_is_bot": None,
        "manifest_path": None,
        "text_path": None,
        "errors": [],
    }
    if download_report is not None:
        download_report.update(result)
        result = download_report

    chat_peer = normalize_chat_reference(chat_id)
    recipients = {}
    recipient_message_ids = set()
    if map_recipients:
        result["recipient_map"] = {
            "bot_id": expected_bot_id,
            "coverage": "observed_outgoing_private_messages",
            "recipients": [],
        }
    if debug_scope:
        result["scope_diagnostics"] = {
            "counts": {"unknown_chat": 0, "authenticated_peer": 0, "different_chat": 0},
            "samples": [],
        }

    client_kwargs = {
        "api_id": int(api_id),
        "api_hash": api_hash,
        "workdir": os.getcwd(),
    }
    if download_auth_mode == "bot":
        client_kwargs["bot_token"] = bot_token_for_auth

    recovery_info = {}
    try:
        with open_download_client(
            Client,
            SessionRevoked,
            session_name,
            client_kwargs,
            recover_revoked_session=download_auth_mode == "bot",
            recovery_info=recovery_info
        ) as app:
            identity = verify_download_identity(app, download_auth_mode, expected_bot_id)
            result.update(recovery_info)
            result["authenticated_user_id"] = identity.id
            result["authenticated_is_bot"] = identity.is_bot
            last_progress_scanned = 0

            def maybe_log_progress(current_message_id=None):
                nonlocal last_progress_scanned
                if not progress_every or progress_every <= 0:
                    return
                scanned = result["messages_scanned"]
                if scanned - last_progress_scanned < progress_every:
                    return
                current_id_part = f", current_message_id={current_message_id}" if current_message_id is not None else ""
                scan_label = "ids_scanned" if result["download_mode_used"] == "idscan" else "messages_scanned"
                unavailable_part = (
                    f", unavailable_ids={result['unavailable_message_ids']}"
                    if result["download_mode_used"] == "idscan" else ""
                )
                recipients_part = f", recipients={len(recipients)}" if map_recipients else ""
                skipped_part = f", skipped_overwrite={result['messages_skipped_overwrite']}" if result["messages_skipped_overwrite"] else ""
                text_print(
                    f"[DOWNLOAD] Progress: {scan_label}={result['messages_scanned']}{unavailable_part}, "
                    f"exported={result['messages_exported']}, filtered={result['messages_filtered']}, "
                    f"media={result['media_downloaded']}, "
                    f"media_reused={result['media_reused']}, "
                    f"media_failed={result['media_failed']}{recipients_part}{skipped_part}{current_id_part}"
                )
                last_progress_scanned = scanned

            resolved_chat_id = chat_peer
            try:
                chat = app.get_chat(chat_peer)
                candidate = getattr(chat, "id", None)
                if type(candidate) is int:
                    resolved_chat_id = candidate
                result["chat_title"] = getattr(chat, "title", None) or getattr(chat, "first_name", None)
                result["chat_type"] = str(getattr(chat, "type", "unknown"))
            except Exception as chat_error:
                result["errors"].append(f"get_chat failed: {chat_error}")

            if type(resolved_chat_id) is not int or resolved_chat_id == 0:
                raise RuntimeError("Unable to resolve the target chat to a numeric ID; acquisition stopped.")
            if type(chat_peer) is int and chat_peer != resolved_chat_id:
                raise RuntimeError("Resolved chat ID does not match the requested target; acquisition stopped.")
            chat_peer = resolved_chat_id
            os.makedirs(download_dir, exist_ok=True)

            effective_stem = output_stem or build_daily_messages_stem(
                result.get("chat_title"), chat_id, acquisition_date
            )
            # Snapshot previous references before today's logs are truncated.
            media_index = {} if skip_media else load_media_reuse_index(
                download_dir, resolved_chat_id, result["errors"]
            )

            with open_message_export(download_dir, effective_stem, result) as (manifest_file, text_file):
                exported_ids = set()
                counter_keys = ("messages_exported", "media_downloaded", "media_reused", "media_failed")

                def export_record(destination, directory, manifest_path, text_path):
                    entry = {"chat_id": destination, "download_dir": display_path(directory),
                             "manifest_path": manifest_path, "text_path": text_path}
                    entry.update(dict.fromkeys(counter_keys, 0))
                    result["chat_exports"].append(entry)
                    return entry

                primary_entry = export_record(chat_peer, download_dir, result["manifest_path"], result["text_path"])
                other_exports = {}

                def write_message(message, destination, directory, manifest, text, index, entry):
                    before = {key: result[key] for key in counter_keys}
                    try:
                        if process_download_message(
                            message, app, destination, directory, manifest, text, result,
                            skip_media=skip_media, hash_media=hash_media, media_index=index
                        ):
                            exported_ids.add((destination, message.id))
                    finally:
                        for key in counter_keys:
                            entry[key] += result[key] - before[key]

                def export_other_chat(message, destination):
                    if destination not in other_exports:
                        directory = os.path.join(os.path.dirname(os.path.abspath(download_dir)), str(destination))
                        title = getattr(getattr(message, "chat", None), "title", None)
                        stem = build_daily_messages_stem(title, destination, acquisition_date)
                        if should_confirm_overwrite(directory, stem):
                            text_print(f"ATTENTION Today's export already exists in: {display_path(directory)}")
                            if overwrite_policy == "never" or (overwrite_policy == "ask" and not confirm_export_overwrite()):
                                other_exports[destination] = None
                                result["skipped_chats"].append(destination)
                                result["errors"].append(f"Export skipped for chat {destination}: today's files were not approved for overwrite.")
                        if destination not in other_exports:
                            os.makedirs(directory, exist_ok=True)
                            index = {} if skip_media else load_media_reuse_index(directory, destination, result["errors"])
                            paths = {}
                            with open_message_export(directory, stem, paths) as (manifest, text):
                                entry = export_record(destination, directory, paths["manifest_path"], paths["text_path"])
                                other_exports[destination] = (directory, index, entry)
                                text_print(f"[DOWNLOAD] Chat export: {display_path(directory)}")
                                write_message(message, destination, directory, manifest, text, index, entry)
                            return
                    state = other_exports[destination]
                    if state is None:
                        result["messages_skipped_overwrite"] += 1
                        return
                    directory, index, entry = state
                    # Only the primary log pair stays open across messages. This
                    # bounds open file handles even when many chats are found.
                    with open(entry["manifest_path"], "a", encoding="utf-8") as manifest, open(
                        entry["text_path"], "a", encoding="utf-8"
                    ) as text:
                        write_message(message, destination, directory, manifest, text, index, entry)

                def export_message(message):
                    if map_recipients:
                        record_recipient(message, identity.id, recipients, recipient_message_ids)
                    message_id = getattr(message, "id", None)
                    destination = getattr(getattr(message, "chat", None), "id", None)
                    if type(destination) is int and (destination, message_id) in exported_ids:
                        return
                    if (download_scope == "token" and type(destination) is int and destination != 0
                            and destination != chat_peer and getattr(message, "date", None)):
                        export_other_chat(message, destination)
                    else:
                        write_message(message, chat_peer, download_dir, manifest_file, text_file, media_index, primary_entry)

                def run_history_download():
                    # Enforce the export limit after chat validation, not on raw results.
                    history_kwargs = {"chat_id": chat_peer}

                    try:
                        history = iter(app.get_chat_history(**history_kwargs))
                    except Exception as error:
                        raise HistoryRetrievalError(str(error)) from error
                    while True:
                        try:
                            message = next(history)
                        except StopIteration:
                            break
                        except Exception as error:
                            raise HistoryRetrievalError(str(error)) from error
                        result["messages_scanned"] += 1
                        export_message(message)
                        maybe_log_progress(getattr(message, "id", None))
                        if history_limit and result["messages_exported"] >= history_limit:
                            break

                def run_id_scan_download(start_id):
                    current_message_id = int(start_id)
                    while current_message_id > 0:
                        count = min(batch_size, current_message_id)
                        if history_limit:
                            remaining = history_limit - result["messages_exported"]
                            if remaining <= 0:
                                break
                            count = min(count, remaining)
                        message_ids = list(range(current_message_id, current_message_id - count, -1))
                        messages = app.get_messages(chat_peer, message_ids, replies=0)
                        # Match by ID: responses may omit IDs or arrive in a different order.
                        messages_by_id = {message.id: message for message in messages}
                        for message_id in message_ids:
                            result["messages_scanned"] += 1
                            message = messages_by_id.get(message_id)
                            if not getattr(message, "date", None):
                                result["unavailable_message_ids"] += 1
                            export_message(message)
                            maybe_log_progress(message_id)
                        current_message_id -= count

                def ensure_start_id():
                    if result["start_message_id"]:
                        return int(result["start_message_id"])
                    if bot_token_for_start:
                        derived_id, cleanup_error = resolve_start_message_id_with_bot(bot_token_for_start, chat_peer)
                        result["start_message_id"] = int(derived_id)
                        if cleanup_error:
                            result["errors"].append(cleanup_error)
                        return int(derived_id)
                    raise RuntimeError(
                        "start message id is required for idscan mode. "
                        "Use --download-start-id or provide a bot token so Tosint can derive it."
                    )

                if download_mode == "history":
                    result["download_mode_used"] = "history"
                    run_history_download()
                elif download_mode == "idscan" or (download_mode == "auto" and download_auth_mode == "bot"):
                    result["download_mode_used"] = "idscan"
                    run_id_scan_download(ensure_start_id())
                else:
                    result["download_mode_used"] = "history"
                    try:
                        run_history_download()
                    except HistoryRetrievalError as history_error:
                        result["errors"].append(f"history mode failed: {history_error}")
                        result["download_mode_used"] = "idscan"
                        if exported_ids:
                            # History is newest-first: continue below the oldest
                            # exported ID without posting a new probe message.
                            next_id = min(message_id for _, message_id in exported_ids) - 1
                            if start_message_id is not None:
                                next_id = min(next_id, start_message_id)
                            result["start_message_id"] = next_id
                        else:
                            next_id = ensure_start_id()
                        run_id_scan_download(next_id)
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["errors"].append("download interrupted by user")
    except Exception as error:
        result["failed"] = True
        result["errors"].append(f"download failed: {error}")
        raise
    finally:
        if map_recipients:
            result["recipient_map"]["recipients"] = [recipients[key] for key in sorted(recipients)]
    return result


def print_download_summary(download_result, default_scope=None):
    if download_result.get("interrupted"):
        text_print("\n[DOWNLOAD] Interrupted by user")
    elif download_result.get("failed"):
        text_print("\n[DOWNLOAD] Failed; partial results preserved")
    else:
        text_print("\n[DOWNLOAD] Completed")
    text_print(f"Requested Mode: {download_result['download_mode_requested']}")
    text_print(f"Used Mode: {download_result['download_mode_used']}")
    text_print(f"Download Scope: {download_result.get('download_scope', default_scope)}")
    if download_result.get("start_message_id"):
        text_print(f"Start Message ID: {download_result['start_message_id']}")
    text_print(f"Download Directory: {download_result.get('download_root', display_path(download_result['download_dir']))}")
    if download_result.get("manifest_path"):
        text_print(f"Manifest: {display_path(download_result['manifest_path'])}")
    if download_result.get("text_path"):
        text_print(f"Text Log: {display_path(download_result['text_path'])}")
    scan_label = "Message IDs Scanned" if download_result['download_mode_used'] == "idscan" else "Messages Scanned"
    text_print(f"{scan_label}: {download_result['messages_scanned']}")
    if download_result['download_mode_used'] == "idscan":
        text_print(f"Unavailable Message IDs: {download_result['unavailable_message_ids']}")
    text_print(f"Messages Exported: {download_result['messages_exported']}")
    text_print(f"Messages Filtered (Other/Unknown Chat): {download_result.get('messages_filtered', 0)}")
    if download_result.get("messages_skipped_overwrite"):
        text_print(f"Messages Skipped (Overwrite Policy): {download_result['messages_skipped_overwrite']}")
    if len(download_result.get("chat_exports", [])) > 1:
        for entry in download_result["chat_exports"]:
            text_print(f"Chat {entry['chat_id']}: exported={entry['messages_exported']}, directory={entry['download_dir']}")
    if "scope_diagnostics" in download_result:
        text_print("Scope Diagnostic Counts: " + json.dumps(download_result["scope_diagnostics"]["counts"]))
    if "recipient_map" in download_result:
        mapped = download_result["recipient_map"]["recipients"]
        text_print(f"Private Recipients Observed (Partial Map): {len(mapped)}")
        for recipient in mapped:
            text_print("Recipient: " + json.dumps(recipient))
    text_print(f"Media Downloaded: {download_result['media_downloaded']}")
    text_print(f"Media Reused: {download_result.get('media_reused', 0)}")
    text_print(f"Media Failed: {download_result['media_failed']}")


def main():
    global TEXT_OUTPUT_ENABLED
    # Initialize the argument parser for command-line parameters
    parser = argparse.ArgumentParser(description='OSINT analysis for Telegram bots.')

    # Add options for token and chat ID
    parser.add_argument('-t', '--token', type=str, help='Telegram Token (bot1xxx)', required=True)
    parser.add_argument('-c', '--chat_id', type=str, help='Telegram Chat ID (-100xxx)', required=False)
    parser.add_argument('--json', action='store_true', help='Print analysis report in JSON format')
    parser.add_argument('--json-file', type=str, help='Save analysis report as JSON file')
    parser.add_argument('--create-invite-link', action='store_true', help='Create an additional chat invite link (requires -c and appropriate bot administrator rights)')
    parser.add_argument('--downloads', '--download', action='store_true', help='Download Telegram chat history and media')
    parser.add_argument('--api-id', type=str, help='Telegram API_ID for MTProto downloads (Kurigram)')
    parser.add_argument('--api-hash', type=str, help='Telegram API_HASH for MTProto downloads (Kurigram)')
    parser.add_argument('--session-name', type=str, default=None, help='Kurigram session name/path override. By default: sessions/kurigram/<bot>_<chat>/<bot|user>, based on --download-auth')
    parser.add_argument('--download-dir', type=str, default='downloads', help='Directory where messages/media are saved (default: downloads)')
    parser.add_argument('--download-overwrite', choices=['ask', 'always', 'never'], default='ask', help="How to handle today's existing export files: ask, always, or never (default: ask)")
    parser.add_argument('--download-limit', type=int, default=0, help='Max messages to export (0 = all)')
    parser.add_argument('--download-mode', type=str, choices=['auto', 'history', 'idscan'], default='auto', help='Download strategy: auto (bot: idscan; user: history with idscan fallback), history, or idscan')
    parser.add_argument('--download-auth', type=str, choices=['bot', 'user'], default='bot', help='Download auth mode: bot (default, uses -t token) or user (interactive login)')
    parser.add_argument('--download-scope', choices=['token', 'chatid'], default=None, help='Export encountered chats separately (token, default for bot) or only -c (chatid, default and only scope for user)')
    parser.add_argument('--download-start-id', type=int, help='Start message_id for idscan mode (latest known message id)')
    parser.add_argument('--download-progress-every', type=int, default=50, help='Print download progress every N scanned messages (0 disables)')
    parser.add_argument('--download-batch-size', type=int, default=50, help='Message IDs per idscan request, from 1 to 200 (default: 50)')
    parser.add_argument('--download-debug-scope', action='store_true', help='Diagnose filtered messages using counts and up to 10 ID-only samples; no message content')
    parser.add_argument('--map-recipients', action='store_true', help='Map observed private recipients of the authenticated bot during --download; save with --json-file')
    parser.add_argument('--skip-media-download', action='store_true', help='Do not download media attachments; export only message metadata/text')
    parser.add_argument('--hash-media', action='store_true', help='Compute SHA-256 of downloaded attachments and include hashes in JSONL (disabled by default)')
    parser.add_argument('--env-file', type=str, default='.env', help='Env file path for API_ID/API_HASH (default: .env)')

    # Parse the command-line arguments
    args = parser.parse_args()
    TEXT_OUTPUT_ENABLED = not args.json
    if not 1 <= args.download_batch_size <= 200:
        parser.error('--download-batch-size must be between 1 and 200')
    if args.download_start_id is not None and args.download_start_id <= 0:
        parser.error('--download-start-id must be greater than zero')
    if args.download_limit < 0:
        parser.error('--download-limit must be zero or greater')
    if not args.token.strip():
        parser.error('-t/--token must not be empty')
    if args.map_recipients and (not args.downloads or args.download_auth != "bot"):
        parser.error('--map-recipients requires --download and --download-auth bot')
    if args.download_scope == "token" and args.download_auth != "bot":
        parser.error('--download-scope token requires --download-auth bot')
    args.download_scope = args.download_scope or ("token" if args.download_auth == "bot" else "chatid")
    if (args.downloads or args.create_invite_link) and not (args.chat_id and args.chat_id.strip()):
        parser.error('--downloads and --create-invite-link require -c/--chat_id')

    report = {"errors": []}
    try:
        # Interactive libraries may print directly instead of using text_print.
        with (redirect_stdout(sys.stderr) if args.json else nullcontext()):
            run_analysis(args, report)
    except TelegramAPIError as error:
        report["errors"].append(str(error))
        text_print(f"ATTENTION {error}")
    except KeyboardInterrupt:
        report["errors"].append("Analysis interrupted by user.")
        text_print("\nAnalysis interrupted by user.")
        emit_json_report(report, args.json, args.json_file)
        return 130
    emit_json_report(report, args.json, args.json_file)
    if report.get("downloads", {}).get("interrupted"):
        return 130
    return 1 if report["errors"] else 0


def run_analysis(args, report):

    env_values = load_env_file(args.env_file)
    # Only API credentials are read from .env by design.
    env_values = {
        "TELEGRAM_API_ID": env_values.get("TELEGRAM_API_ID"),
        "TELEGRAM_API_HASH": env_values.get("TELEGRAM_API_HASH"),
    }

    run_bot_analysis = True

    telegram_token = get_value(
        args.token,
        env_values,
        env_key=None,
        prompt_text=None
    )
    if not telegram_token:
        text_print("ATTENTION Telegram token is required.")
        return
    if telegram_token.startswith('bot'):
        telegram_token = telegram_token[3:]

    telegram_chat_id = get_value(
        args.chat_id,
        env_values,
        env_key=None,
        prompt_text=None
    )
    if args.downloads and not telegram_chat_id:
        text_print("ATTENTION Telegram chat id/username is required when using --downloads.")
        return
    report.update({
        "input": {
            "token": telegram_token,
            "chat_id": telegram_chat_id,
        },
        "bot": {},
        "chat": {},
        "invite_links": {},
        "admins": [],
        "downloads": {},
        "errors": [],
    })

    if run_bot_analysis:
        if telegram_chat_id:
            text_print(f"\nAnalysis of token: {telegram_token} and chat id: {telegram_chat_id}")
        else:
            text_print(f"\nAnalysis of token: {telegram_token}")

    def perform_downloads(target_download_dir, bot_token_for_start, session_name, chat_title_for_files=None):
        if not args.downloads:
            return
        resolved_download_auth = args.download_auth
        if resolved_download_auth == "bot" and not bot_token_for_start:
            report["errors"].append("download auth mode 'bot' requires a valid bot token.")
            text_print("ATTENTION download auth mode 'bot' requires a valid bot token.")
            return
        output_stem = build_daily_messages_stem(chat_title_for_files, telegram_chat_id)
        if should_confirm_overwrite(target_download_dir, output_stem):
            text_print(
                f"ATTENTION Today's export already exists in: {display_path(target_download_dir)}"
            )
            if args.download_overwrite == "never":
                text_print("Download phase skipped because --download-overwrite is set to never.")
                report["errors"].append("download skipped because today's export already existed and overwrite policy was set to never")
                return
            if args.download_overwrite == "ask":
                if not confirm_export_overwrite():
                    text_print("Download phase skipped by user.")
                    report["errors"].append("download skipped by user because today's export already existed")
                    return

        print_section("DOWNLOAD")
        text_print("Starting requested download phase...")
        text_print(f"Requested Mode: {args.download_mode}")
        text_print(f"Auth Mode: {resolved_download_auth}")
        text_print(f"Download Scope: {args.download_scope}")
        text_print(f"Session: {display_path(session_name)}")
        output_directory = os.path.dirname(os.path.abspath(target_download_dir)) if args.download_scope == "token" else target_download_dir
        text_print(f"Output Directory: {display_path(output_directory)}")
        if args.skip_media_download:
            text_print("Media download is disabled (--skip-media-download).")

        api_id = get_value(
            args.api_id,
            env_values,
            env_key="TELEGRAM_API_ID",
            prompt_text="Telegram API_ID: "
        )
        api_hash = get_value(
            args.api_hash,
            env_values,
            env_key="TELEGRAM_API_HASH",
            prompt_text="Telegram API_HASH: "
        )
        if not api_id or not api_hash:
            report["errors"].append("TELEGRAM_API_ID and TELEGRAM_API_HASH are required for --downloads.")
            text_print("ATTENTION TELEGRAM_API_ID and TELEGRAM_API_HASH are required for --downloads.")
        else:
            download_result = {}
            report["downloads"] = download_result
            try:
                download_result = download_chat_content(
                    chat_id=telegram_chat_id,
                    api_id=api_id,
                    api_hash=api_hash,
                    session_name=session_name,
                    download_dir=target_download_dir,
                    history_limit=args.download_limit,
                    download_mode=args.download_mode,
                    start_message_id=args.download_start_id,
                    bot_token_for_start=bot_token_for_start,
                    bot_token_for_auth=bot_token_for_start,
                    download_auth_mode=resolved_download_auth,
                    progress_every=args.download_progress_every,
                    skip_media=args.skip_media_download,
                    output_stem=output_stem,
                    batch_size=args.download_batch_size,
                    hash_media=args.hash_media,
                    expected_bot_id=telegram_get_me["id"],
                    debug_scope=args.download_debug_scope,
                    map_recipients=args.map_recipients,
                    download_scope=args.download_scope,
                    overwrite_policy=args.download_overwrite,
                    download_report=download_result
                )
                report["downloads"] = download_result
                if download_result.get("skipped_chats"):
                    report["errors"].append("Some chat exports were skipped because today's files were not approved for overwrite.")
            except Exception as error:
                report["errors"].append(f"downloads error: {error}")
                text_print(f"ATTENTION downloads error: {error}")
            if download_result:
                print_download_summary(download_result, args.download_scope)

    # Get Bot Info
    telegram_get_me_response = get_bot_info(telegram_token)
    telegram_get_me = telegram_get_me_response.get("result")

    # If the response contains bot information, print the relevant details
    if telegram_get_me:
        bot_username = telegram_get_me.get("username")
        print_section("BOT")
        last_error_description = None
        text_print(f"Bot First Name: {telegram_get_me['first_name']}")
        text_print(f"Bot Username: {telegram_get_me['username']}")
        text_print(f"Bot User ID: {telegram_get_me['id']}")
        print_field(telegram_get_me, "can_read_all_group_messages", "Bot Can Read All Group Messages")
        report["bot"]["first_name"] = telegram_get_me.get("first_name")
        report["bot"]["username"] = telegram_get_me.get("username")
        report["bot"]["user_id"] = telegram_get_me.get("id")
        report["bot"]["can_read_all_group_messages"] = telegram_get_me.get("can_read_all_group_messages")

        # Get Bot Description
        bot_description_response = get_bot_description(telegram_token)
        bot_description = bot_description_response.get("result")
        if bot_description:
            if "description" in bot_description and bot_description["description"] is not None:
                desc = normalize_single_line(bot_description["description"])
                if desc:
                    text_print(f"Bot Description: {desc}")
                    report["bot"]["description"] = desc

        # Get Bot Short Description
        bot_short_description_response = get_bot_short_description(telegram_token)
        bot_short_description = bot_short_description_response.get("result")
        if bot_short_description:
            if "short_description" in bot_short_description and bot_short_description["short_description"] is not None:
                short_desc = normalize_single_line(bot_short_description["short_description"])
                if short_desc:
                    text_print(f"Bot Short Description: {short_desc}")
                    report["bot"]["short_description"] = short_desc

        enrich_bot_info(telegram_token, report)

        # Get Bot Default Admin Rights (groups/supergroups)
        default_admin_rights_response = get_default_admin_rights(telegram_token, for_channels=False)
        default_admin_rights = default_admin_rights_response.get("result")
        if default_admin_rights:
            text_print(f"Bot Default Requested Administrator Rights (groups/supergroups): {format_output_value(default_admin_rights)}")
            report["bot"]["default_admin_rights_groups"] = default_admin_rights

        # Get Bot Default Admin Rights (channels)
        default_admin_rights_channels_response = get_default_admin_rights(telegram_token, for_channels=True)
        default_admin_rights_channels = default_admin_rights_channels_response.get("result")
        if default_admin_rights_channels:
            text_print(f"Bot Default Requested Administrator Rights (channels): {format_output_value(default_admin_rights_channels)}")
            report["bot"]["default_admin_rights_channels"] = default_admin_rights_channels

        # Get Bot Status - Member or Admin

        bot_chat_member_response = get_bot_chat_member(telegram_token, telegram_chat_id, telegram_get_me['id']) if telegram_chat_id else {}
        if bot_chat_member_response.get('result'):
            telegram_get_chat_member = bot_chat_member_response.get('result')
            text_print(f"Bot Chat Membership Status: {telegram_get_chat_member['status']}")
            report["bot"]["status_in_chat"] = telegram_get_chat_member.get("status")
        elif bot_chat_member_response.get('description'):
            error_description = bot_chat_member_response.get('description')
            if bot_chat_member_response.get('parameters') and 'migrate_to_chat_id' in bot_chat_member_response.get('parameters'):
                text_print(f"ATTENTION {error_description} - Migrated to: {bot_chat_member_response.get('parameters')['migrate_to_chat_id']}")
            else:
                text_print(f"ATTENTION {error_description}")
            last_error_description = error_description
            report["errors"].append(error_description)

        if not telegram_chat_id:
            text_print("\n[CHAT]")
            text_print("Chat ID not provided. Skipping chat and admins analysis.")
            return

        # Get Chat Info

        get_chat_response = get_chat_info(telegram_token, telegram_chat_id)
        telegram_get_chat = get_chat_response.get('result')

        if not telegram_get_chat:
            if get_chat_response.get('description'):
                error_description = get_chat_response.get('description')
                if error_description != last_error_description:
                    text_print(f"ATTENTION {error_description}")
                report["errors"].append(error_description)
            else:
                text_print("ATTENTION Chat ID is invalid, inaccessible, or no longer available.")
                report["errors"].append("Chat ID is invalid, inaccessible, or no longer available.")
            return

        print_section("CHAT")
        print_chat_summary(telegram_get_chat)
        report["chat"] = dict(telegram_get_chat)
        if report["chat"].get("description"):
            report["chat"]["description"] = normalize_single_line(report["chat"]["description"])
        if "linked_chat_id" in telegram_get_chat and telegram_get_chat["linked_chat_id"]:
            linked_chat_id = telegram_get_chat["linked_chat_id"]
            linked_chat_response = get_chat_info(telegram_token, linked_chat_id)
            linked_chat = linked_chat_response.get('result')
            if linked_chat:
                print_linked_chat_summary(linked_chat)
                report["chat"]["linked_chat"] = linked_chat
            elif linked_chat_response.get('description'):
                text_print(f"ATTENTION linked_chat_id getChat error: {linked_chat_response.get('description')}")
                report["errors"].append(f"linked_chat_id getChat error: {linked_chat_response.get('description')}")


        created_invite_link = None
        if args.create_invite_link:
            create_invite_response = create_chat_invite_link(telegram_token, telegram_chat_id)
            if create_invite_response.get("ok"):
                created_invite_link = create_invite_response.get("result", {}).get("invite_link")
            else:
                create_error = create_invite_response.get("description", "Unknown Telegram API error")
                text_print(f"ATTENTION createChatInviteLink error: {create_error}")
                report["errors"].append(f"createChatInviteLink error: {create_error}")

        print_invite_links(telegram_get_chat.get('invite_link'), created_invite_link)
        report["invite_links"] = {
            "chat_invite_link": telegram_get_chat.get("invite_link"),
            "created": created_invite_link,
        }

        # Get Chat Member Count

        chat_member_count_response = get_chat_member_count(telegram_token, telegram_chat_id)
        telegram_chat_members_count = chat_member_count_response.get('result')

        text_print(f"Chat Member Count: {telegram_chat_members_count}")
        report["chat"]["member_count"] = telegram_chat_members_count

        # Get Administrators in chat

        chat_administrators_response = get_chat_administrators(telegram_token, telegram_chat_id) if telegram_get_chat.get("type") != "private" else {}
        telegram_get_chat_administrators = chat_administrators_response.get('result')
        if chat_administrators_response.get("ok") is False:
            admin_error = f"getChatAdministrators: {chat_administrators_response.get('description', 'Unknown Telegram API error')}"
            text_print(f"ATTENTION {admin_error}")
            report["errors"].append(admin_error)

        if telegram_get_chat_administrators:
            print_section("ADMINS")
            text_print(f"Administrators in the chat:")
            for index, chat_member in enumerate(telegram_get_chat_administrators, start=1):
                print_admin_details(chat_member, index)
                report["admins"].append(build_admin_json(chat_member, index))
        scoped_session_name = build_scoped_session_name(args.session_name, telegram_chat_id, bot_username, args.download_auth)
        perform_downloads(
            build_bot_download_dir(args.download_dir, bot_username, telegram_get_chat.get("id") or telegram_chat_id),
            telegram_token,
            scoped_session_name,
            telegram_get_chat.get("title")
        )
    else:
        if telegram_get_me_response.get("error_code") == 401:
            error_message = "Telegram token is invalid or revoked."
        else:
            error_message = f"Bot token validation failed: {telegram_get_me_response.get('description', 'Unexpected getMe response')}"
        text_print(error_message)
        report["errors"].append(error_message)
        if args.downloads:
            text_print("Download phase skipped because bot token validation failed.")


if __name__ == '__main__':
    sys.exit(main())
