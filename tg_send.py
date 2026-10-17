#!/usr/bin/env python3
"""
tg_send.py - Universal Proactive Telegram Media & File Sender for Antigravity Agent
Allows the AI agent to send photos, videos, audio, voice notes, animations, documents,
or text notifications directly to the user on Telegram.
Automatically detects media type by file extension and records delivered files to avoid duplicates.
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from typing import Optional
import config
from config import TRANSIENT_MSGS_FILE, TURN_SENT_FILES_FILE
from auth_manager import auth_mgr

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".aac"}
VOICE_EXTS = {".ogg", ".opus"}
ANIM_EXTS = {".gif"}


def _get_target_chat_id(explicit_chat_id: Optional[str] = None) -> Optional[int]:
    if explicit_chat_id and str(explicit_chat_id).lstrip("-").isdigit():
        return int(explicit_chat_id)
    if config.ALLOWED_USER_ID:
        return int(config.ALLOWED_USER_ID)
    return auth_mgr.get_primary_admin_id()


def _record_transient_msg(msg_id: int) -> None:
    try:
        data = []
        if TRANSIENT_MSGS_FILE.exists():
            with open(TRANSIENT_MSGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        if msg_id not in data:
            data.append(msg_id)
        TRANSIENT_MSGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TRANSIENT_MSGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _record_sent_file(file_path: Path) -> None:
    try:
        resolved = str(file_path.resolve())
        data = []
        if TURN_SENT_FILES_FILE.exists():
            with open(TURN_SENT_FILES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        if resolved not in data:
            data.append(resolved)
        TURN_SENT_FILES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TURN_SENT_FILES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def send_message(text: str, parse_mode: str = "HTML", chat_id: Optional[int] = None, transient: bool = True) -> bool:
    token = config.TELEGRAM_BOT_TOKEN
    target = chat_id or _get_target_chat_id()
    if not token or not target:
        print("Error: TELEGRAM_BOT_TOKEN or target chat_id missing in .env", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": target, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(url, json=payload, timeout=15)
        res = r.json()
        if not res.get("ok"):
            payload.pop("parse_mode", None)
            r = requests.post(url, json=payload, timeout=15)
            res = r.json()
        if res.get("ok"):
            msg_id = res.get("result", {}).get("message_id")
            if msg_id and transient:
                _record_transient_msg(msg_id)
            return True
        return False
    except Exception as e:
        print(f"Error sending Telegram message: {e}", file=sys.stderr)
        return False


def send_media_or_file(
    file_path: str,
    caption: str = "",
    media_type: str = "auto",
    chat_id: Optional[int] = None,
) -> bool:
    """
    Send any file (photo, video, audio, voice, animation, or document) to Telegram.
    Automatically picks the optimal Telegram API endpoint and falls back to sendDocument if needed.
    """
    token = config.TELEGRAM_BOT_TOKEN
    target = chat_id or _get_target_chat_id()
    if not token or not target:
        print("Error: TELEGRAM_BOT_TOKEN or target chat_id missing in .env", file=sys.stderr)
        return False

    p = Path(file_path)
    if not p.is_file():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return False

    size_mb = p.stat().st_size / (1024 * 1024)
    ext = p.suffix.lower()

    if media_type == "auto":
        if ext in PHOTO_EXTS and size_mb <= 10:
            media_type = "photo"
        elif ext in VIDEO_EXTS and size_mb <= 49:
            media_type = "video"
        elif ext in AUDIO_EXTS and size_mb <= 49:
            media_type = "audio"
        elif ext in VOICE_EXTS and size_mb <= 49:
            media_type = "voice"
        elif ext in ANIM_EXTS and size_mb <= 49:
            media_type = "animation"
        else:
            media_type = "document"

    endpoint_map = {
        "photo": ("sendPhoto", "photo"),
        "video": ("sendVideo", "video"),
        "audio": ("sendAudio", "audio"),
        "voice": ("sendVoice", "voice"),
        "animation": ("sendAnimation", "animation"),
        "document": ("sendDocument", "document"),
    }
    method, field_name = endpoint_map.get(media_type, ("sendDocument", "document"))

    def _attempt_upload(api_method: str, form_field: str) -> bool:
        url = f"https://api.telegram.org/bot{token}/{api_method}"
        try:
            with open(p, "rb") as f:
                files = {form_field: (p.name, f)}
                data = {"chat_id": target}
                if api_method == "sendVideo":
                    data["supports_streaming"] = "true"
                if caption:
                    data["caption"] = caption[:1024]
                    data["parse_mode"] = "HTML"
                r = requests.post(url, data=data, files=files, timeout=120)
                res = r.json()
                if not res.get("ok") and caption:
                    # Retry without HTML parse_mode in case caption had raw characters
                    f.seek(0)
                    data.pop("parse_mode", None)
                    r = requests.post(url, data=data, files=files, timeout=120)
                    res = r.json()
                return bool(res.get("ok"))
        except Exception as e:
            print(f"Warning during {api_method}: {e}", file=sys.stderr)
            return False

    ok = _attempt_upload(method, field_name)
    if not ok and method != "sendDocument":
        # Fallback to generic document upload
        ok = _attempt_upload("sendDocument", "document")

    if ok:
        _record_sent_file(p)
        print(f"✅ Fichier envoyé sur Telegram ({media_type}) : {p.name}")
        return True

    print(f"❌ Échec de l'envoi Telegram pour : {p.name}", file=sys.stderr)
    return False


# Backward-compatible alias
send_document = send_media_or_file


def main():
    parser = argparse.ArgumentParser(description="Send messages, photos, videos, audio, or documents to Telegram")
    parser.add_argument("message", nargs="?", default="", help="Text message or caption")
    parser.add_argument("--file", "-f", default="", help="File path to send (auto-detects photo/video/audio/document)")
    parser.add_argument("--photo", default="", help="Send explicitly as inline photo")
    parser.add_argument("--video", default="", help="Send explicitly as inline video")
    parser.add_argument("--audio", default="", help="Send explicitly as audio track")
    parser.add_argument("--voice", default="", help="Send explicitly as voice note")
    parser.add_argument("--document", default="", help="Send explicitly as document attachment")
    parser.add_argument("--caption", "-c", default="", help="Caption for the media/file")
    parser.add_argument("--chat-id", default="", help="Optional target Telegram chat ID")
    parser.add_argument("--permanent", action="store_true", help="Do not auto-delete text message at end of turn")
    args = parser.parse_args()

    target_chat = _get_target_chat_id(args.chat_id)
    cap = args.caption or args.message

    if args.photo:
        sys.exit(0 if send_media_or_file(args.photo, cap, media_type="photo", chat_id=target_chat) else 1)
    if args.video:
        sys.exit(0 if send_media_or_file(args.video, cap, media_type="video", chat_id=target_chat) else 1)
    if args.audio:
        sys.exit(0 if send_media_or_file(args.audio, cap, media_type="audio", chat_id=target_chat) else 1)
    if args.voice:
        sys.exit(0 if send_media_or_file(args.voice, cap, media_type="voice", chat_id=target_chat) else 1)
    if args.document:
        sys.exit(0 if send_media_or_file(args.document, cap, media_type="document", chat_id=target_chat) else 1)
    if args.file:
        sys.exit(0 if send_media_or_file(args.file, cap, media_type="auto", chat_id=target_chat) else 1)

    text = args.message
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    if not text:
        parser.print_help()
        sys.exit(1)

    ok = send_message(text, chat_id=target_chat, transient=not args.permanent)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()