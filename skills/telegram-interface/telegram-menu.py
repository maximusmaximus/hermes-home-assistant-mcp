#!/usr/bin/env python3
"""
Telegram Interactive Menu & Button Dispatcher
Supports:
1. Persistent Bottom Reply Keyboards (Kitchen Sink navigation pinned to screen)
2. Interactive Inline Button Cards (Contextual actions and sub-menus)
"""
import argparse
import json
import os
import sys
import requests

DEFAULT_PERSISTENT_BUTTONS = [
    ["💡 Lights & Zones", "🌡️ Climate & Sensors"],
    ["⚡ Power & Switches", "📋 Shopping List & To-Do"],
    ["🎬 Scenes & Presets", "🛡️ MCP Security & Health"],
]

def unescape_text(text: str) -> str:
    """
    Decodes literal escape sequences (like \\n, \\r, \\t) passed through CLI shells
    or agent environments so that Telegram receives genuine line breaks rather than
    literal visible slashes.
    """
    if not text:
        return text
    for _ in range(3):
        if r"\n" not in text and r"\r" not in text and r"\t" not in text:
            break
        text = text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n").replace(r"\t", "\t")
    return text


def parse_args():
    parser = argparse.ArgumentParser(description="Send interactive Telegram button menus.")
    parser.add_argument("--token", default=os.getenv("TELEGRAM_BOT_TOKEN"), help="Telegram bot token")
    parser.add_argument("--chat-id", default=os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")[0], help="Target chat ID")
    parser.add_argument("--title", required=True, help="Header / Title in bold")
    parser.add_argument("--subtitle", default="", help="Optional descriptive text")
    parser.add_argument("--button", action="append", default=[], help="Inline button in format 'Label' or 'Label:callback_data' or 'Label:https://url'")
    parser.add_argument("--cols", type=int, default=2, help="Columns per inline button row (default: 2)")
    parser.add_argument("--persistent", action="store_true", help="Send a persistent bottom reply keyboard menu")
    parser.add_argument("--custom-persistent", action="append", default=[], help="Row of persistent buttons separated by commas, e.g. 'Btn1,Btn2'")
    return parser.parse_args()

def build_inline_keyboard(buttons, cols=2):
    rows = []
    current_row = []
    for btn in buttons:
        if ":" in btn:
            parts = btn.split(":", 1)
            label = unescape_text(parts[0].strip())
            target = parts[1].strip()
        else:
            label = unescape_text(btn.strip())
            target = label

        if target.startswith("http://") or target.startswith("https://"):
            btn_obj = {"text": label, "url": target}
        else:
            btn_obj = {"text": label, "callback_data": target[:64]}

        current_row.append(btn_obj)
        if len(current_row) >= cols:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)
    return {"inline_keyboard": rows}

def build_persistent_keyboard(custom_rows=None):
    if custom_rows:
        keyboard = []
        for r in custom_rows:
            keyboard.append([{"text": unescape_text(item.strip())} for item in r.split(",") if item.strip()])
    else:
        keyboard = [[{"text": unescape_text(btn)} for btn in row] for row in DEFAULT_PERSISTENT_BUTTONS]

    return {
        "keyboard": keyboard,
        "resize_keyboard": True,
        "is_persistent": True
    }

def main():
    args = parse_args()
    token = args.token
    chat_id = args.chat_id

    if not token or not chat_id:
        print("Error: Missing bot token or chat ID.", file=sys.stderr)
        sys.exit(1)

    title = unescape_text(args.title)
    text_parts = [title]
    if args.subtitle:
        subtitle = unescape_text(args.subtitle)
        text_parts.append(subtitle)
    message_text = "\n\n".join(text_parts)

    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "Markdown",
    }

    if args.persistent:
        payload["reply_markup"] = build_persistent_keyboard(args.custom_persistent)
    elif args.button:
        payload["reply_markup"] = build_inline_keyboard(args.button, cols=args.cols)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json=payload, timeout=10)
        res = r.json()
        if res.get("ok"):
            print(f"Success: Message sent (ID: {res['result']['message_id']})")
        else:
            print(f"Telegram API Error: {res}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Request Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
