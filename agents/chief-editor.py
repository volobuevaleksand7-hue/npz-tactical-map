#!/usr/bin/env python3
"""Главный редактор (24.10.2026): каждые 30 мин следит, что срочные ролики реально вышли.
Без модели. Слот прошёл >30 мин, а ролика нет на YouTube → чинит, что умеет (аудит ок + файл есть → заливает),
иначе шлёт владельцу ТГ-алерт (раз на причину). Накопилось ≥2 невыложенных — не заливает скопом, зовёт на склейку."""
import json, os, subprocess, sys, time, datetime as dt, urllib.parse, urllib.request
ROOT = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
OUT = f"{ROOT}/video/out"
STATE = f"{OUT}/chief-editor-state.json"
LATE_MIN = 30
MAX_BURST, BURST_WIN = 2, 60

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
        if "slot" not in e: continue   # служебные записи {"asked": ...} от urgent_gate
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
    # правило владельца (24.10): не больше MAX_BURST роликов за BURST_WIN мин — иначе бан
    recent = sum(1 for f in os.listdir(OUT) if f.startswith("urgent-") and f.endswith(".uploaded")
                 and time.time() - os.path.getmtime(f"{OUT}/{f}") < BURST_WIN * 60)
    room = MAX_BURST - recent
    if room > 0 and ready and len(stuck) <= MAX_BURST:
        for e, _, _ in ready[:room]:
            a = subprocess.run(["python3", f"{ROOT}/video/reel/audit.py", e["date"], e["kind"]], capture_output=True, text=True, cwd=f"{ROOT}/video")
            if a.returncode != 0:
                key = f"audit:{e['kind']}"
                if key not in state:
                    state[key] = int(time.time())
                    alert(f"🟠 Главред: {e['kind']} собран, но аудит не прошёл:\n{(a.stdout or a.stderr)[-400:]}")
                continue
            for cmd in ("upload.py", "tg_post.py"):
                subprocess.run(["python3", cmd, e["kind"], e["date"]], cwd=f"{ROOT}/video")
            alert(f"🎬 Главред: {e['kind']} задержался, залил сам.")
    else:
        key = "backlog:" + ",".join(sorted(p[0]["kind"] for p in stuck)) + f":{recent}"
        if key not in state:
            state[key] = int(time.time())
            alert("🟠 Главред: не вышли " + ", ".join(p[0]["kind"] + (" (собран)" if p[1] else " (нет файла)") for p in stuck)
                  + f". Больше {MAX_BURST} за {BURST_WIN} мин не заливаю (бан) — нужна склейка в один ролик.")
    json.dump(state, open(STATE, "w"))

if __name__ == "__main__":
    main()
