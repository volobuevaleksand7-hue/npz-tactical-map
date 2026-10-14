#!/usr/bin/env python3
"""Сводка по международке и ИТН в Telegram-канал раз в 3 дня.

  tg-world-digest.py [--dry] [--force] [--days 3] [--state P]

Канал и бот те же, что у hermes/bot/send_to_channel.py (@NPZmap, токен ~/.npz-bot/token).
Cron запускает скрипт ежедневно; отправка только если с прошлой успешной прошло >= days
календарных дней (state: ~/.npz-bot/world-digest-state.json). --dry печатает текст и
ничего не шлёт и не пишет в state. Данные: data/world/{index,index-history,events}.json.
Режим ОЦЕНКА: OSINT, не официальные данные.
"""
import argparse
import datetime as dt
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "hermes", "bot"))
DATA = os.path.join(ROOT, "data", "world")
STATE = os.path.expanduser("~/.npz-bot/world-digest-state.json")
SITE = "https://npz-tactical-map.vercel.app"
MSK = dt.timezone(dt.timedelta(hours=3))

REGION_RU = {"europe": "Европа", "russia_cis": "Россия и СНГ", "middle_east": "Ближний Восток",
             "east_asia": "Восточная Азия", "south_asia": "Южная Азия",
             "north_america": "Северная Америка", "latin_america": "Латинская Америка",
             "africa": "Африка"}
STATUS_RU = {"confirmed": "подтверждено", "reported": "сообщается", "rumored": "неподтверждённо"}


def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def cut(s, n=170):
    s = " ".join(str(s).split())
    if len(s) <= n:
        return s
    return s[:n].rsplit(" ", 1)[0].rstrip(",;:—- ") + "…"


def delta_text(index, history, today, days):
    cur = index["world"]["value"]
    base = None
    for h in sorted(history, key=lambda x: x["date"]):
        if h["date"] <= (today - dt.timedelta(days=days)).isoformat() and h.get("world") is not None:
            base = h
    note = f"за {days} дн."
    if base is None:  # истории не хватает: берём самую раннюю запись и честно пишем срок
        old = [h for h in sorted(history, key=lambda x: x["date"]) if h.get("world") is not None
               and h["date"] < today.isoformat()]
        if not old:
            return None
        base = old[0]
        n = (today - dt.date.fromisoformat(base["date"])).days
        note = f"за {n} дн., история короче"
    d = cur - base["world"]
    sign = "+" if d > 0 else ("−" if d < 0 else "")
    return f"{sign}{abs(d)} {note}" if d else f"без изменений {note}"


def pick_events(events, today, days, limit=3):
    def pool(span):
        lo = (today - dt.timedelta(days=span)).isoformat()
        return [e for e in events if e.get("review") == "approved" and (e.get("occurred_at") or "") >= lo
                and e.get("status") in ("confirmed", "reported")]
    p = pool(days)
    if len(p) < 2:
        p = pool(days * 2 + 1)
    p.sort(key=lambda e: e.get("occurred_at") or "", reverse=True)
    p.sort(key=lambda e: e.get("status") != "confirmed")  # стабильно: confirmed первыми
    return p[:limit]


def build(today, days):
    index = load("index.json", None)
    if not index or "world" not in index:
        raise SystemExit("нет data/world/index.json")
    history = load("index-history.json", [])
    events = load("events.json", {}).get("events", [])
    w = index["world"]
    dtext = delta_text(index, history, today, days)
    head = f"Индекс топливной напряжённости (ИТН): мир {w['value']}/100, уровень «{w['level_ru']}»"
    if dtext:
        head += f" ({dtext})"
    lines = ["<b>Международная топливная ситуация</b>", "", html.escape(head + "."), ""]
    regs = sorted(((k, v) for k, v in index.get("regions", {}).items() if v.get("value") is not None),
                  key=lambda kv: -kv[1]["value"])[:4]
    lines.append("<b>Выше всего ИТН:</b>")
    for k, v in regs:
        lines.append(html.escape(f"• {REGION_RU.get(k, v.get('name', k))}: {v['value']} ({v['level_ru']})"))
    evs = pick_events(events, today, days)
    if evs:
        lines += ["", "<b>События за последние дни:</b>"]
        for e in evs:
            st = STATUS_RU.get(e.get("status"), e.get("status"))
            lines.append(html.escape(f"• {e['occurred_at'][8:10]}.{e['occurred_at'][5:7]} "
                                     f"{cut(e['title'])} ({st})"))
    news = os.path.join(ROOT, "world", "news")
    latest = sorted(f for f in os.listdir(news) if f.endswith(".html")) if os.path.isdir(news) else []
    lines.append("")
    lines.append(f'Карта и методика: <a href="{SITE}/world">{SITE}/world</a>')
    if latest:
        d = latest[-1][:-5]
        lines.append(f'Свежий выпуск «Всемирные новости»: <a href="{SITE}/world/news/{d}">{d}</a>')
    lines += ["", "<i>Оценка, OSINT: неофициальные данные, показатели расчётные.</i>"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true", help="игнорировать интервал (не для cron)")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--state", default=STATE)
    a = ap.parse_args()
    today = dt.datetime.now(MSK).date()
    last = None
    try:
        last = dt.date.fromisoformat(json.load(open(a.state)).get("last_sent", ""))
    except Exception:
        pass
    due = a.force or last is None or (today - last).days >= a.days
    text = build(today, a.days)
    if a.dry:
        print(text)
        print(f"\n[dry] последняя отправка: {last or 'нет'}; к отправке сегодня: {'да' if due else 'нет'}", file=sys.stderr)
        return 0
    if not due:
        print(f"SKIP: последняя отправка {last}, интервал {a.days} дн.")
        return 0
    from send_to_channel import send
    r = send(text)
    if not r.get("ok"):
        print(f"ошибка отправки: {r}", file=sys.stderr)
        return 1
    tmp = a.state + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"last_sent": today.isoformat(), "message_id": r["result"]["message_id"]}, f)
    os.replace(tmp, a.state)
    print(f"OK: message_id={r['result']['message_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
