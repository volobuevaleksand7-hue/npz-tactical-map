#!/usr/bin/env python3
"""Рилс дня -> Telegram-канал (@npz_karta_online) АНОНИМНЫМ ботом канала.

  python3 video/tg_post.py reel 2026-10-02

Токен и список каналов — hermes/bot/channel_mirror.py (mirror_token, CHANNEL_MIRRORS): только
анонимный бот, личный @NpzFuel_Bot сюда не ходит. Нет токена — тихий пропуск.
Видео пережимается до 720×1280 (лимит Bot API — 50 МБ). Подпись — .build/reel-<дата>/tg_caption.txt
+ ссылка на YouTube из data/videos.json. Повтор не шлёт: маркер out/reel-<дата>.tg.
Только stdlib + ffmpeg.
"""
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

VIDEO = Path(__file__).resolve().parent
ROOT = VIDEO.parent
sys.path.insert(0, str(ROOT / "hermes" / "bot"))
import channel_mirror as CM  # noqa: E402


def log(m):
    print(f"tg_post: {m}", flush=True)


def send_video(token, chat, path: Path, caption):
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", chat), ("caption", caption), ("parse_mode", "HTML"),
                 ("supports_streaming", "true"), ("width", "720"), ("height", "1280")):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="video"; filename="{path.name}"\r\n'
                 f'Content-Type: video/mp4\r\n\r\n'.encode() + path.read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendVideo", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": e.read().decode(errors="replace")[:300]}


def main():
    a = sys.argv[1:]
    if len(a) != 2 or not (a[0] in ("reel", "reel-evening", "urgent") or a[0].startswith("urgent-")):   # urgent-<метка> — второй срочный за дату
        sys.exit(__doc__)
    kind, date = a
    src = VIDEO / "out" / f"{kind}-{date}.mp4"
    mark = VIDEO / "out" / f"{kind}-{date}.tg"
    if mark.exists():
        return log(f"{date}: уже в канале")
    if not src.exists():
        return log(f"{date}: нет {src.name}")
    if os.environ.get("NPZ_REEL_TG", "1") != "1":
        return log("выключено NPZ_REEL_TG")
    token = CM.mirror_token()
    if not token:
        return log("нет токена анонимного бота — пропуск")
    cap_f = VIDEO / ".build" / f"{kind}-{date}" / "tg_caption.txt"
    caption = cap_f.read_text(encoding="utf-8").strip() if cap_f.exists() else f"🎬 Удары за {date}"
    try:
        yt = json.loads((ROOT / "data" / "videos.json").read_text(encoding="utf-8"))["videos"][date][kind]["id"]
        caption += f'\n▶ <a href="https://youtu.be/{yt}">YouTube</a>'
    except (OSError, ValueError, KeyError):
        pass
    small = VIDEO / "out" / f"{kind}-{date}.tg.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", "scale=720:1280",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(small)], check=True)
    if small.stat().st_size > 49 * 1024 * 1024:
        small.unlink()
        return log(f"{date}: после сжатия > 49 МБ — пропуск")
    ok = False
    for chat in CM.CHANNEL_MIRRORS:
        r = send_video(token, chat, small, caption[:1024])
        log(f"{date} -> {chat}: {'ok' if r.get('ok') else r}")
        ok = ok or bool(r.get("ok"))
    small.unlink(missing_ok=True)
    if ok:
        mark.write_text(date + "\n")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
