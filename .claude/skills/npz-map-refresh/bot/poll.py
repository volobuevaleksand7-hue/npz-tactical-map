#!/usr/bin/env python3
# poll.py — собрать новых подписчиков бота @NpzFuel_Bot через Telegram getUpdates
# (long-poll без вебхука; подходит для ручного/локального пайплайна карты).
# Обрабатывает /start (подписка), /stop (отписка), /status. Хранит подписчиков и
# offset в ~/.npz-bot/ (вне репозитория). Запускать перед broadcast и/или по крону.
import json, os, sys, time, urllib.request, urllib.parse, importlib.util

HOME = os.path.expanduser("~")

# подгружаем broadcast.py как модуль (для мгновенного дайджеста новому подписчику)
try:
    _spec = importlib.util.spec_from_file_location("npzbroadcast", os.path.join(os.path.dirname(__file__), "broadcast.py"))
    _bc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_bc)
except Exception:
    _bc = None
BOT_DIR = os.path.join(HOME, ".npz-bot")
TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "poll-state.json")
API = "https://api.telegram.org/bot" + TOKEN
SITE = "https://npz-tactical-map.vercel.app"

WELCOME = ("✅ Вы подписаны на сводку «Топливный фронт РФ».\n\n"
           "После каждого обновления карты пришлю кратко: новые удары по НПЗ, ситуацию "
           "на АЗС и голоса людей — со ссылкой на карту.\n\n"
           "Открыть карту: " + SITE + "\nОтписаться: /stop")
BYE = "Вы отписались. Вернуться — /start."

def jload(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def api(method, **params):
    data = urllib.parse.urlencode(params).encode()
    try:
        r = urllib.request.urlopen(API + "/" + method, data=data, timeout=40)
        return json.loads(r.read().decode())
    except Exception as e:
        print("api err", method, e); return {}

def now_utc():
    import datetime; return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def main():
    subsdoc = jload(SUBS_PATH, {"subscribers": {}})
    subs = subsdoc.setdefault("subscribers", {})
    st = jload(STATE_PATH, {})
    offset = st.get("offset", 0)

    added = removed = 0
    resp = api("getUpdates", offset=offset, timeout=0, allowed_updates=json.dumps(["message"]))
    for u in resp.get("result", []):
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        cid = str(chat.get("id") or "")
        text = (msg.get("text") or "").strip().lower()
        if not cid: continue
        if text.startswith("/start"):
            info = subs.get(cid, {})
            new = info.get("status") != "active"
            info.update({"status":"active", "since": info.get("since") or now_utc(),
                         "src": (text.split(None,1)[1] if " " in text else info.get("src","")),
                         "name": chat.get("first_name") or chat.get("username") or ""})
            subs[cid] = info
            if new: added += 1
            api("sendMessage", chat_id=cid, text=WELCOME, disable_web_page_preview="true")
            # мгновенная стартовая сводка новому подписчику (свежие данные, без ожидания прогона)
            if new and _bc is not None:
                try:
                    txt, _ = _bc.compute_digest(force_latest=True)
                    _bc.send(cid, txt)
                except Exception as e:
                    print("welcome-digest err", e)
        elif text.startswith("/stop"):
            if subs.get(cid, {}).get("status") == "active":
                subs[cid]["status"] = "stopped"; removed += 1
            api("sendMessage", chat_id=cid, text=BYE)
        elif text.startswith("/status"):
            active = subs.get(cid, {}).get("status") == "active"
            api("sendMessage", chat_id=cid, text=("Подписка активна ✅" if active else "Вы не подписаны. /start"))

    json.dump(subsdoc, open(SUBS_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"offset": offset}, open(STATE_PATH,"w",encoding="utf-8"))
    active = sum(1 for v in subs.values() if v.get("status")=="active")
    print("poll: +%d новых, -%d отписок | активных подписчиков: %d" % (added, removed, active))

if __name__ == "__main__":
    main()
