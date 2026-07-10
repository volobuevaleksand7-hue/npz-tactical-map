#!/usr/bin/env python3
"""Send text message to @NPZmap channel via @NpzFuel_Bot API."""
import json
import os
import sys
import urllib.request
import urllib.parse

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
TOKEN_PATH = os.path.join(BOT_DIR, "token")
CHANNEL_ID = "-1004491068477"

def send(text, parse_mode="HTML"):
    with open(TOKEN_PATH) as f:
        token = f.read().strip()
    payload = json.dumps({
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: send_to_channel.py <message_file_or_text>", file=sys.stderr)
        sys.exit(1)
    arg = sys.argv[1]
    if os.path.isfile(arg):
        with open(arg, encoding="utf-8") as f:
            text = f.read()
    else:
        text = arg
    result = send(text)
    print(f"OK: message_id={result['result']['message_id']}")
