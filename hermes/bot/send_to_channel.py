#!/usr/bin/env python3
"""Send text message to @NPZmap channel via @NpzFuel_Bot API.

Она же — единственная точка, через которую джоба NPZ NEWSWATCH (Hermes cron,
~/.hermes/cron/jobs.json) шлёт в канал и молнии, и пустые почасовые отчёты
«За последний час новых ударов ... не зафиксировано». Владелец решил
2026-08-01: пустые отчёты — шум (2 просмотра, забивают ленту между реальными
новостями), молчим вместо поста; реальный удар (текст с МОЛНИЯ) уходит как
раньше — фильтр смотрит только на признак «пусто», не трогает остальное.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from channel_mirror import send_to_mirrors, mirror_enabled  # noqa: E402

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
TOKEN_PATH = os.path.join(BOT_DIR, "token")
CHANNEL_ID = "-1004491068477"

# ponytail: сигнатура пустого почасового отчёта NEWSWATCH — «не зафиксировано»
# и отсутствие формата МОЛНИЯ (реальный удар всегда идёт через render_molniya,
# начинается с "🚨 МОЛНИЯ"). Если LLM когда-нибудь начнёт писать иначе и фильтр
# перестанет ловить пустые отчёты — аварийный откат: NPZ_SEND_EMPTY_RADAR=1
# восстанавливает старое поведение (шлём всё) без правки кода.
_EMPTY_RADAR_RE = re.compile(r"не\s+зафиксировано", re.IGNORECASE)


def is_empty_radar_report(text):
    """True — похоже на пустой почасовой отчёт («новых ударов не зафиксировано»),
    а не на реальный алерт. Реальные молнии (содержат «МОЛНИЯ») никогда не режутся."""
    text = text or ""
    return bool(_EMPTY_RADAR_RE.search(text)) and "МОЛНИЯ" not in text


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

    if is_empty_radar_report(text) and os.environ.get("NPZ_SEND_EMPTY_RADAR", "0") != "1":
        print("SKIP: пустой почасовой радар-отчёт подавлен (NPZ_SEND_EMPTY_RADAR=1 — вернуть старое поведение)")
        sys.exit(0)

    result = send(text)
    print(f"OK: message_id={result['result']['message_id']}")

    if "МОЛНИЯ" in text and mirror_enabled("NPZ_MIRROR_MOLNIYA"):
        send_to_mirrors(text, label="молния (newswatch)")
