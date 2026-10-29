#!/usr/bin/env python3
"""Пост для вкладки «Сообщество» YouTube (API постов не даёт): готовим картинку + текст и шлём владельцу в Telegram
одним сообщением — копировать и нажать «Опубликовать» (29.10.2026, просьба владельца).
  python3 video/reel/community_post.py [kind] [date]     kind: reel | reel-evening | urgent-<id6>"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "video" / "out"
SITE = "https://npz-tactical-map.vercel.app/"


def bot():
    return (Path("/root/.npz-bot/token").read_text().strip(), Path("/root/.npz-bot/chat_id").read_text().strip())


def build(kind, date):
    txt = (OUT / f"{kind}-{date}.txt").read_text(encoding="utf-8").splitlines()
    title = re.sub(r"\s*#shorts\s*$", "", txt[0]).strip()
    rows = []
    for ln in txt:
        if ln.startswith("— ") and "t.me" not in ln and "http" not in ln:
            place, _, rest = ln[2:].partition(": ")
            what = re.split(r"(?<=[.!?])\s", rest, 1)[0].rstrip(".")
            rows.append(f"• {place}: {what}")
    body = "\n".join(rows[:6])
    text = f"{title}\n\n{body}\n\nКарта и сводка дня: {SITE}news/{date}.html\n#НПЗ #ТопливныйФронт"
    img = REPO / "assets" / f"cover-{date}.png"
    return text[:1000], img


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "reel"
    date = sys.argv[2] if len(sys.argv) > 2 else __import__("datetime").date.today().isoformat()
    text, img = build(kind, date)
    t, c = bot()
    hint = "📌 Пост для вкладки «Сообщество» (YouTube Studio → Создать → Публикация): сохрани картинку, вставь текст ниже.\n\n"
    cap = hint + text
    r = subprocess.run(["curl", "-s", "-F", f"chat_id={c}", "-F", f"photo=@{img}", "-F", f"caption={cap[:1024]}",
                        f"https://api.telegram.org/bot{t}/sendPhoto"], capture_output=True, text=True)
    print(r.stdout[:200])


if __name__ == "__main__":
    main()
