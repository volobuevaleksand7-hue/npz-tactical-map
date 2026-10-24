#!/usr/bin/env python3
"""Главный редактор (24.10.2026): каждые 30 мин следит, что срочные ролики реально вышли.
Без модели. Слот прошёл >30 мин, а ролика нет на YouTube → чинит, что умеет (аудит ок + файл есть → заливает),
иначе шлёт владельцу ТГ-алерт (раз на причину). Накопилось ≥2 невыложенных — не заливает скопом, зовёт на склейку."""
import json, os, subprocess, sys, time, datetime as dt, urllib.parse, urllib.request
ROOT = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
OUT = f"{ROOT}/video/out"
STATE = f"{OUT}/chief-editor-state.json"
LATE_MIN = 30

def alert(text):
    try:
        t = open("/root/.npz-bot/token").read().strip(); c = open("/root/.npz-bot/chat_id").read().strip()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{t}/sendMessage",
            data=urllib.parse.urlencode({"chat_id": c, "text": text}).encode()), timeout=20)
    except Exception as e:
        print("alert failed:", e)

def main():
    now = dt.datetime.now(dt.timezone.utc)
    try: state = json.load(open(STATE))
    except Exception: state = {}
    log = json.load(open(f"{OUT}/urgent-log.json"))
    log = log if isinstance(log, list) else log.get("items", [])
    pending = []
    for e in log:
        slot = dt.datetime.fromisoformat(e["slot"])
        kind, date = e["kind"], e["date"]
        if (now - slot).total_seconds() < LATE_MIN * 60 or (now - slot).total_seconds() > 36 * 3600: continue
        if os.path.exists(f"{OUT}/{kind}-{date}.uploaded"): continue
        mp4 = os.path.exists(f"{OUT}/{kind}-{date}.mp4")
        busy = subprocess.run(["pgrep", "-f", f"daily.sh {date}"], capture_output=True).stdout.strip()
        pending.append((e, mp4, bool(busy)))
    stuck = [p for p in pending if not p[2]]
    if not stuck:
        json.dump(state, open(STATE, "w")); return
    ready = [p for p in stuck if p[1]]
    if len(ready) == 1 and len(stuck) == 1:
        e = ready[0][0]
        a = subprocess.run(["python3", f"{ROOT}/video/reel/audit.py", e["date"], e["kind"]], capture_output=True, text=True, cwd=f"{ROOT}/video")
        if a.returncode == 0:
            for cmd in ("upload.py", "tg_post.py"):
                subprocess.run(["python3", cmd, e["kind"], e["date"]], cwd=f"{ROOT}/video")
            alert(f"🎬 Главред: {e['kind']} задержался, залил сам.")
            return
        key = f"audit:{e['kind']}"
        if key not in state:
            state[key] = int(time.time())
            alert(f"🟠 Главред: {e['kind']} собран, но аудит не прошёл:\n{(a.stdout or a.stderr)[-400:]}")
    else:
        key = "backlog:" + ",".join(sorted(p[0]["kind"] for p in stuck))
        if key not in state:
            state[key] = int(time.time())
            alert("🟠 Главред: не вышли " + ", ".join(p[0]["kind"] + (" (собран)" if p[1] else " (нет файла)") for p in stuck)
                  + ". Скопом не заливаю — нужна склейка в один ролик.")
    json.dump(state, open(STATE, "w"))

if __name__ == "__main__":
    main()
