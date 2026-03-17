#!/usr/bin/env python3
import os
import json
import requests
import argparse
import mimetypes
from datetime import datetime

TEXT_OUTPUT_ENABLED = True


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
    print_field(chat, "is_direct_messages", "Chat Is Direct Messages")
    print_field(chat, "has_visible_history", "Chat Has Visible History")
    print_field(chat, "has_hidden_members", "Chat Has Hidden Members")
    print_field(chat, "has_protected_content", "Chat Has Protected Content")
    print_field(chat, "join_to_send_messages", "Join Required To Send")
    print_field(chat, "join_by_request", "Join Requires Admin Approval")
    print_field(chat, "slow_mode_delay", "Slow Mode Delay (s)")
    print_field(chat, "message_auto_delete_time", "Message Auto Delete Time (s)")
    print_field(chat, "linked_chat_id", "Linked Chat ID")
    if "location" in chat and chat["location"]:
        text_print(f"Chat Location: {format_output_value(chat['location'])}")

    if "permissions" in chat and chat["permissions"]:
        text_print(f"Default Chat Permissions: {format_output_value(chat['permissions'])}")

    if "pinned_message" in chat and chat["pinned_message"]:
        pinned = chat["pinned_message"]
        text_print("Pinned Message:")
        print_field(pinned, "message_id", "  Message ID")
        print_field(pinned, "date", "  Date (unix)")
        print_field(pinned, "author_signature", "  Author Signature")
        print_field(pinned, "text", "  Text")
        if "from" in pinned and pinned["from"]:
            text_print(f"  From: {pinned['from']}")
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
    print_field(chat_member, "status", "  Status")
    print_field(chat_member, "custom_title", "  Custom Title")
    permissions = extract_admin_permissions(chat_member)
    if permissions:
        text_print(f"  Permissions: {format_output_value(permissions)}")


def telegram_api_get(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.get(url, params=params)
    return response.json()


def telegram_api_post(token, method, data=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, data=data)
    return response.json()


def get_bot_info(token):
    return telegram_api_get(token, "getMe")


def get_bot_description(token):
    return telegram_api_get(token, "getMyDescription")


def get_bot_short_description(token):
    return telegram_api_get(token, "getMyShortDescription")


def get_default_admin_rights(token, for_channels=False):
    params = {"for_channels": "true"} if for_channels else None
    return telegram_api_get(token, "getMyDefaultAdministratorRights", params=params)


def get_bot_chat_member(token, chat_id, user_id):
    params = {"chat_id": chat_id, "user_id": user_id}
    return telegram_api_get(token, "getChatMember", params=params)


def get_chat_info(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "getChat", params=params)


def export_chat_invite_link(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "exportChatInviteLink", params=params)


def create_chat_invite_link(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "createChatInviteLink", params=params)


def get_chat_member_count(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "getChatMemberCount", params=params)


def get_chat_administrators(token, chat_id):
    params = {"chat_id": chat_id}
    return telegram_api_get(token, "getChatAdministrators", params=params)


def send_message(token, chat_id, text):
    data = {"chat_id": chat_id, "text": text}
    return telegram_api_post(token, "sendMessage", data=data)


def delete_message(token, chat_id, message_id):
    data = {"chat_id": chat_id, "message_id": message_id}
    return telegram_api_post(token, "deleteMessage", data=data)


def print_invite_links(chat_invite_link, exported_invite_link, created_invite_link):
    if not chat_invite_link and not exported_invite_link and not created_invite_link:
        text_print("Invite Links: None")
        return
    text_print("Invite Links:")
    text_print(f"  Chat Invite Link: {chat_invite_link}")
    text_print(f"  Chat Invite Link (exported): {exported_invite_link}")
    text_print(f"  Chat Invite Link (created): {created_invite_link}")


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
    report_payload = json.dumps(report, indent=2, ensure_ascii=False)
    if print_json:
        print(report_payload)
    if json_file:
        try:
            with open(json_file, "w", encoding="utf-8") as file_obj:
                file_obj.write(report_payload)
                file_obj.write("\n")
            text_print(f"\nJSON report saved to: {json_file}")
        except OSError as error:
            text_print(f"\nATTENTION Unable to save JSON report to '{json_file}': {error}")


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


def get_value(cli_value, env_values, env_key=None, prompt_text=None):
    if cli_value is not None and str(cli_value).strip():
        return str(cli_value).strip()
    if env_key and env_values.get(env_key):
        return env_values[env_key].strip()
    if prompt_text:
        return input(prompt_text).strip()
    return None


def message_to_json(message, downloaded_file=None):
    from_user = getattr(message, "from_user", None)
    sender_chat = getattr(message, "sender_chat", None)
    date_value = getattr(message, "date", None)
    if isinstance(date_value, datetime):
        date_value = date_value.isoformat()
    media_type = None
    if getattr(message, "media", None):
        media_type = str(message.media)

    if downloaded_file:
        downloaded_file = display_path(downloaded_file)

    return {
        "message_id": getattr(message, "id", None),
        "date": date_value,
        "from_user_id": getattr(from_user, "id", None) if from_user else None,
        "from_username": getattr(from_user, "username", None) if from_user else None,
        "sender_chat_id": getattr(sender_chat, "id", None) if sender_chat else None,
        "text": getattr(message, "text", None),
        "caption": getattr(message, "caption", None),
        "media_type": media_type,
        "downloaded_file": downloaded_file,
    }


def message_to_text(message, downloaded_file=None):
    date_value = getattr(message, "date", None)
    if isinstance(date_value, datetime):
        date_value = date_value.isoformat()
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


def build_bot_download_dir(base_download_dir, bot_username):
    bot_segment = sanitize_path_segment(bot_username or "unknown_bot")
    return os.path.join(base_download_dir, bot_segment)


def build_scoped_session_name(cli_session_name, chat_id, bot_username=None):
    if cli_session_name:
        return cli_session_name
    chat_segment = sanitize_path_segment(chat_id)
    bot_segment = sanitize_path_segment(bot_username) if bot_username else "unknown_bot"
    return os.path.join("sessions", f"{bot_segment}_{chat_segment}", "tosint_user")


def display_path(path_value):
    try:
        return os.path.relpath(path_value, os.getcwd())
    except ValueError:
        return path_value


def ensure_dir_path(path_value):
    if path_value.endswith(os.sep):
        return path_value
    return path_value + os.sep


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

    message_id = getattr(message, "id", "unknown")
    inferred_ext = infer_media_extension(message) or ""
    return f"media_{message_id}{inferred_ext}"


def build_unique_media_target(message, media_dir):
    original_name = infer_media_filename(message)
    base_name = sanitize_path_segment(original_name)
    stem, ext = os.path.splitext(base_name)
    message_id = getattr(message, "id", "unknown")
    unique_name = f"{message_id}_{stem}{ext}"
    return os.path.join(media_dir, unique_name)


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


def process_download_message(message, app, chat_id, download_dir, manifest_file, text_file, result, skip_media=False):
    if not getattr(message, "date", None):
        return False

    downloaded_file = None
    media_type_str = str(getattr(message, "media", "")) if getattr(message, "media", None) else ""
    is_web_preview = "WEB_PAGE_PREVIEW" in media_type_str or "WEBPAGE" in media_type_str.upper()

    if getattr(message, "media", None) and not skip_media and not is_web_preview:
        try:
            media_dir = os.path.join(download_dir, "media")
            os.makedirs(media_dir, exist_ok=True)
            target_file = build_unique_media_target(message, media_dir)
            downloaded_file = app.download_media(message, file_name=target_file)
            downloaded_file = normalize_downloaded_media_path(downloaded_file, message)
            if downloaded_file:
                result["media_downloaded"] += 1
            else:
                result["media_failed"] += 1
                result["errors"].append(
                    f"message_id={getattr(message, 'id', None)} download returned no file path"
                )
        except Exception as download_error:
            result["media_failed"] += 1
            result["errors"].append(
                f"message_id={getattr(message, 'id', None)} download error: {download_error}"
            )

    message_payload = message_to_json(message, downloaded_file=downloaded_file)
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

    delete_response = delete_message(bot_token, chat_id, message_id)
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
    download_auth_mode="auto",
    progress_every=50,
    skip_media=False,
    output_stem=None
):
    try:
        from pyrogram import Client
    except ImportError as error:
        raise RuntimeError(
            "Pyrofork is not installed. Run: pip install pyrofork"
        ) from error

    os.makedirs(download_dir, exist_ok=True)
    session_dir = os.path.dirname(session_name)
    if session_dir:
        os.makedirs(session_dir, exist_ok=True)
    result = {
        "chat_id": str(chat_id),
        "session_name": session_name,
        "download_dir": display_path(download_dir),
        "history_limit": history_limit,
        "download_mode_requested": download_mode,
        "download_mode_used": None,
        "start_message_id": start_message_id,
        "chat_title": None,
        "chat_type": None,
        "messages_scanned": 0,
        "messages_exported": 0,
        "media_downloaded": 0,
        "media_failed": 0,
        "interrupted": False,
        "manifest_path": None,
        "text_path": None,
        "errors": [],
    }

    chat_peer = normalize_chat_reference(chat_id)

    client_kwargs = {
        "api_id": int(api_id),
        "api_hash": api_hash,
    }
    if download_auth_mode == "bot":
        if not bot_token_for_auth:
            raise RuntimeError("download auth mode 'bot' requires a valid bot token.")
        client_kwargs["bot_token"] = bot_token_for_auth

    try:
        with Client(session_name, **client_kwargs) as app:
            last_progress_scanned = 0

            def maybe_log_progress(current_message_id=None):
                nonlocal last_progress_scanned
                if not progress_every or progress_every <= 0:
                    return
                scanned = result["messages_scanned"]
                if scanned - last_progress_scanned < progress_every:
                    return
                current_id_part = f", current_message_id={current_message_id}" if current_message_id is not None else ""
                text_print(
                    f"[DOWNLOAD] Progress: scanned={result['messages_scanned']}, "
                    f"exported={result['messages_exported']}, media={result['media_downloaded']}, "
                    f"media_failed={result['media_failed']}{current_id_part}"
                )
                last_progress_scanned = scanned

            try:
                chat = app.get_chat(chat_peer)
                result["chat_title"] = getattr(chat, "title", None) or getattr(chat, "first_name", None)
                result["chat_type"] = str(getattr(chat, "type", "unknown"))
            except Exception as chat_error:
                result["errors"].append(f"get_chat failed: {chat_error}")

            effective_stem = output_stem or build_messages_stem(result.get("chat_title"), chat_id)
            manifest_path = os.path.join(download_dir, f"{effective_stem}.jsonl")
            text_path = os.path.join(download_dir, f"{effective_stem}.txt")
            result["manifest_path"] = display_path(manifest_path)
            result["text_path"] = display_path(text_path)

            with open(manifest_path, "w", encoding="utf-8") as manifest_file, open(text_path, "w", encoding="utf-8") as text_file:
                def run_history_download():
                    history_kwargs = {"chat_id": chat_peer}
                    if history_limit and history_limit > 0:
                        history_kwargs["limit"] = history_limit

                    for message in app.get_chat_history(**history_kwargs):
                        result["messages_scanned"] += 1
                        process_download_message(
                            message,
                            app,
                            chat_peer,
                            download_dir,
                            manifest_file,
                            text_file,
                            result,
                            skip_media=skip_media
                        )
                        maybe_log_progress(getattr(message, "id", None))

                def run_id_scan_download(start_id):
                    current_message_id = int(start_id)
                    # If history_limit is 0, scan everything down to message_id=1.
                    target_messages = int(history_limit) if history_limit and history_limit > 0 else current_message_id

                    while current_message_id > 0 and result["messages_exported"] < target_messages:
                        result["messages_scanned"] += 1
                        message = app.get_messages(chat_peer, current_message_id)
                        process_download_message(
                            message,
                            app,
                            chat_peer,
                            download_dir,
                            manifest_file,
                            text_file,
                            result,
                            skip_media=skip_media
                        )
                        maybe_log_progress(current_message_id)
                        current_message_id -= 1

                def ensure_start_id():
                    if result["start_message_id"]:
                        return int(result["start_message_id"])
                    if bot_token_for_start:
                        derived_id, cleanup_error = resolve_start_message_id_with_bot(bot_token_for_start, chat_id)
                        result["start_message_id"] = int(derived_id)
                        if cleanup_error:
                            result["errors"].append(cleanup_error)
                        return int(derived_id)
                    raise RuntimeError(
                        "start message id is required for idscan mode. "
                        "Use --download-start-id or provide a bot token so Tosint can derive it."
                    )

                if download_mode == "history":
                    run_history_download()
                    result["download_mode_used"] = "history"
                elif download_mode == "idscan":
                    run_id_scan_download(ensure_start_id())
                    result["download_mode_used"] = "idscan"
                else:
                    try:
                        run_history_download()
                        result["download_mode_used"] = "history"
                    except Exception as history_error:
                        result["errors"].append(f"history mode failed: {history_error}")
                        run_id_scan_download(ensure_start_id())
                        result["download_mode_used"] = "idscan"
    except KeyboardInterrupt:
        result["interrupted"] = True
        result["errors"].append("download interrupted by user")

    return result


def main():
    global TEXT_OUTPUT_ENABLED
    # Initialize the argument parser for command-line parameters
    parser = argparse.ArgumentParser(description='OSINT analysis for Telegram bots.')

    # Add options for token and chat ID
    parser.add_argument('-t', '--token', type=str, help='Telegram Token (bot1xxx)', required=True)
    parser.add_argument('-c', '--chat_id', type=str, help='Telegram Chat ID (-100xxx)', required=False)
    parser.add_argument('--json', action='store_true', help='Print analysis report in JSON format')
    parser.add_argument('--json-file', type=str, help='Save analysis report as JSON file')
    parser.add_argument('--downloads', '--download', action='store_true', help='Download Telegram chat history and media using a user account session')
    parser.add_argument('--api-id', type=str, help='Telegram API_ID for user session (Pyrofork)')
    parser.add_argument('--api-hash', type=str, help='Telegram API_HASH for user session (Pyrofork)')
    parser.add_argument('--session-name', type=str, default=None, help='Pyrofork session name/path. If omitted, Tosint creates a scoped session per bot+chat under sessions/')
    parser.add_argument('--download-dir', type=str, default='downloads', help='Directory where messages/media are saved (default: downloads)')
    parser.add_argument('--download-limit', type=int, default=0, help='Max messages to export (0 = all)')
    parser.add_argument('--download-mode', type=str, choices=['auto', 'history', 'idscan'], default='auto', help='Download strategy: auto (history then idscan fallback), history, or idscan')
    parser.add_argument('--download-auth', type=str, choices=['bot', 'user'], default='bot', help='Download auth mode: bot (default, uses -t token) or user (interactive login)')
    parser.add_argument('--download-start-id', type=int, help='Start message_id for idscan mode (latest known message id)')
    parser.add_argument('--download-progress-every', type=int, default=50, help='Print download progress every N scanned messages (0 disables)')
    parser.add_argument('--skip-media-download', action='store_true', help='Do not download media attachments; export only message metadata/text')
    parser.add_argument('--env-file', type=str, default='.env', help='Env file path for API_ID/API_HASH (default: .env)')

    # Parse the command-line arguments
    args = parser.parse_args()
    TEXT_OUTPUT_ENABLED = not args.json

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

    report = {
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
    }

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

        print_section("DOWNLOAD")
        text_print("Starting requested download phase...")
        text_print(f"Requested Mode: {args.download_mode}")
        text_print(f"Auth Mode: {resolved_download_auth}")
        text_print(f"Session: {display_path(session_name)}")
        text_print(f"Output Directory: {display_path(target_download_dir)}")
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
                    output_stem=build_messages_stem(chat_title_for_files, telegram_chat_id)
                )
                report["downloads"] = download_result
                if download_result.get("interrupted"):
                    text_print("\n[DOWNLOAD] Interrupted by user")
                else:
                    text_print("\n[DOWNLOAD] Completed")
                text_print(f"Requested Mode: {download_result['download_mode_requested']}")
                text_print(f"Used Mode: {download_result['download_mode_used']}")
                if download_result.get("start_message_id"):
                    text_print(f"Start Message ID: {download_result['start_message_id']}")
                text_print(f"Download Directory: {display_path(download_result['download_dir'])}")
                text_print(f"Manifest: {display_path(download_result['manifest_path'])}")
                text_print(f"Text Log: {display_path(download_result['text_path'])}")
                text_print(f"Messages Scanned: {download_result['messages_scanned']}")
                text_print(f"Messages Exported: {download_result['messages_exported']}")
                text_print(f"Media Downloaded: {download_result['media_downloaded']}")
                text_print(f"Media Failed: {download_result['media_failed']}")
            except Exception as error:
                report["errors"].append(f"downloads error: {error}")
                text_print(f"ATTENTION downloads error: {error}")

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
        text_print(f"Bot Can Read Group Messages: {format_output_value(telegram_get_me['can_read_all_group_messages'])}")
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

        # Get Bot Default Admin Rights (groups/supergroups)
        default_admin_rights_response = get_default_admin_rights(telegram_token, for_channels=False)
        default_admin_rights = default_admin_rights_response.get("result")
        if default_admin_rights:
            text_print(f"Bot Default Administrator Rights (groups): {format_output_value(default_admin_rights)}")
            report["bot"]["default_admin_rights_groups"] = default_admin_rights

        # Get Bot Default Admin Rights (channels)
        default_admin_rights_channels_response = get_default_admin_rights(telegram_token, for_channels=True)
        default_admin_rights_channels = default_admin_rights_channels_response.get("result")
        if default_admin_rights_channels:
            text_print(f"Bot Default Administrator Rights (channels): {format_output_value(default_admin_rights_channels)}")
            report["bot"]["default_admin_rights_channels"] = default_admin_rights_channels

        # Get Bot Status - Member or Admin

        bot_chat_member_response = get_bot_chat_member(telegram_token, telegram_chat_id, telegram_get_me['id'])
        if bot_chat_member_response.get('result'):
            telegram_get_chat_member = bot_chat_member_response.get('result')
            text_print(f"Bot In The Chat Is An: {telegram_get_chat_member['status']}")
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
            emit_json_report(report, args.json, args.json_file)
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
            emit_json_report(report, args.json, args.json_file)
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


        # Export Chat Invite Link

        export_invite_response = export_chat_invite_link(telegram_token, telegram_chat_id)
        exported_invite_link = export_invite_response.get("result")

        # Create Chat Invite Link

        create_invite_response = create_chat_invite_link(telegram_token, telegram_chat_id)
        created_invite_link_result = create_invite_response.get('result')
        created_invite_link = None
        if created_invite_link_result and "invite_link" in created_invite_link_result:
            created_invite_link = created_invite_link_result["invite_link"]

        print_invite_links(telegram_get_chat.get('invite_link'), exported_invite_link, created_invite_link)
        report["invite_links"] = {
            "chat_invite_link": telegram_get_chat.get("invite_link"),
            "exported": exported_invite_link,
            "created": created_invite_link,
        }

        # Get Chat Member Count

        chat_member_count_response = get_chat_member_count(telegram_token, telegram_chat_id)
        telegram_chat_members_count = chat_member_count_response.get('result')

        text_print(f"Number of users in the chat: {telegram_chat_members_count}")
        report["chat"]["member_count"] = telegram_chat_members_count

        # Get Administrators in chat

        chat_administrators_response = get_chat_administrators(telegram_token, telegram_chat_id)
        telegram_get_chat_administrators = chat_administrators_response.get('result')

        if telegram_get_chat_administrators:
            print_section("ADMINS")
            text_print(f"Administrators in the chat:")
            for index, chat_member in enumerate(telegram_get_chat_administrators, start=1):
                print_admin_details(chat_member, index)
                report["admins"].append(build_admin_json(chat_member, index))
        scoped_session_name = build_scoped_session_name(args.session_name, telegram_chat_id, bot_username)
        perform_downloads(
            build_bot_download_dir(args.download_dir, bot_username),
            telegram_token,
            scoped_session_name,
            telegram_get_chat.get("title")
        )
        emit_json_report(report, args.json, args.json_file)
    else:
        text_print('Telegram token is invalid or revoked.')
        report["errors"].append("Telegram token is invalid or revoked.")
        text_print("Download phase skipped because bot token validation failed.")
        emit_json_report(report, args.json, args.json_file)


if __name__ == '__main__':
    main()
