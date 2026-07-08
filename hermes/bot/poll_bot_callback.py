#!/usr/bin/env python3
"""
poll_bot_callback.py — Long-poll for Telegram inline-callback buttons.
Listens for callback_query updates, dispatches to radar_publish.handle_callback().

Run as systemd daemon: npz-callback-poll.service
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", os.path.join(HOME, "npz-tactical-map"))

TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
API = "https://api.telegram.org/bot" + TOKEN

sys.path.insert(0, os.path.join(REPO, "hermes", "bot"))
from radar_publish import handle_callback


def get_updates(offset=None, timeout=30):
    params = {"timeout": timeout, "allowed_updates": json.dumps(["callback_query"])}
    if offset is not None:
        params["offset"] = offset
    data = urllib.parse.urlencode(params).encode()
    try:
        req = urllib.request.Request(API + "/getUpdates", data=data)
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[{time.strftime('%H:%M:%S')}] HTTP {e.code}: {body[:200]}", flush=True)
        return None
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}", flush=True)
        return None


def main():
    print(f"[{time.strftime('%H:%M:%S')}] NPZ Callback Poll starting...", flush=True)
    offset = None

    while True:
        result = get_updates(offset=offset, timeout=30)
        if result is None:
            time.sleep(5)
            continue

        if not result.get("ok"):
            print(f"[{time.strftime('%H:%M:%S')}] API error: {result.get('description', 'unknown')}", flush=True)
            time.sleep(10)
            continue

        updates = result.get("result", [])
        for update in updates:
            offset = update["update_id"] + 1
            callback_query = update.get("callback_query")
            if not callback_query:
                continue

            data = callback_query.get("data", "")
            from_id = callback_query.get("from", {}).get("id")
            msg_id = callback_query.get("message", {}).get("message_id")
            print(f"[{time.strftime('%H:%M:%S')}] Callback from {from_id}, msg={msg_id}, data={data[:60]}", flush=True)

            try:
                handled = handle_callback(callback_query)
                if handled:
                    print(f"  -> handled OK", flush=True)
                else:
                    print(f"  -> unhandled (not our button)", flush=True)
            except Exception as e:
                print(f"  -> ERROR: {e}", flush=True)


if __name__ == "__main__":
    main()
