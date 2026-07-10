#!/usr/bin/env python3
"""Send briefing to both @NpzFuel_Bot and @BPLAlert_bot subscribers."""
import json, os, subprocess, sys

REPO = "/root/npz-tactical-map"
BROADCAST = f"{REPO}/hermes/bot/broadcast.py"
HOME = os.path.expanduser("~")

BOTS = {
    "fuel": {"token_dir": os.path.join(HOME, ".npz-bot"), "subs_path": os.path.join(HOME, ".npz-bot", "subscribers.json")},
    "bpl": {"token_dir": os.path.join(HOME, ".npz-bot-bpl"), "subs_path": os.path.join(HOME, ".npz-bot-bpl", "subscribers.json")},
}

def get_subscribers(bot_name):
    try:
        data = json.load(open(BOTS[bot_name]["subs_path"]))
        return data.get("subscribers", {})
    except: return {}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"
    dry = "--dry-run" in sys.argv

    # 1. @NpzFuel_Bot — обычная отправка
    print(f"=== @NpzFuel_Bot ({mode}) ===")
    env = os.environ.copy()
    env["NPZ_REPO"] = REPO
    env["NPZ_BOT_DIR"] = os.path.join(HOME, ".npz-bot")
    r = subprocess.run(
        [sys.executable, BROADCAST, "--briefing", mode] + (["--dry-run"] if dry else []),
        capture_output=True, text=True, timeout=120, env=env
    )
    print(r.stdout[:500])

    # 2. @BPLAlert_bot — через --test для каждого подписчика
    print(f"\n=== @BPLAlert_bot ({mode}) ===")
    bpl_subs = get_subscribers("bpl")
    active = {k: v for k, v in bpl_subs.items() if v.get("status") == "active"}

    if not active:
        print("No active BPLAlert subscribers")
        return

    sent = 0
    for chat_id, sub in active.items():
        if dry:
            print(f"  Would send to {chat_id} ({sub.get('name', '?')})")
            sent += 1
            continue

        env_bpl = env.copy()
        env_bpl["NPZ_BOT_DIR"] = os.path.join(HOME, ".npz-bot-bpl")
        r = subprocess.run(
            [sys.executable, BROADCAST, "--briefing", mode, "--test", chat_id],
            capture_output=True, text=True, timeout=120, env=env_bpl
        )
        if "ok" in r.stdout.lower() or r.returncode == 0:
            sent += 1
            print(f"  Sent to {chat_id} ({sub.get('name', '?')})")
        else:
            print(f"  Failed {chat_id}: {r.stdout[:100]}")

    print(f"BPLAlert: sent {sent}/{len(active)}")

if __name__ == "__main__":
    main()
