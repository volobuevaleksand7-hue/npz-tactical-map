#!/usr/bin/env python3
"""Ежедневный отчёт по каналу владельцу: сколько пришло НОВЫХ и сколько новых ушло.

Зачем не «за сутки»: 31.07.2026 в канал разово залили 1239 накрученных аккаунтов, и на их
фоне живой приход не виден. Поэтому ведём поимённый список пришедших ПОСЛЕ базовой отметки,
а уход считаем раздельно:
  • ушло новых      — ушёл тот, кто пришёл уже при нас (реальная потеря)
  • отвал накрутки  — ушёл кто-то из базы (её Telegram и должен вычищать)

Bot API отдаёт только итоговое число участников; поимённо приход/уход есть лишь в журнале
действий канала, поэтому читаем его юзерботом-создателем. Журнал живёт ~48 ч, а прогон идёт
по id последнего разобранного события — пропуск одного дня переживём, двух уже нет.

env: NPZ_REPORT_CHAT (кому), NPZ_REPORT_TOKEN (файл токена бота-отправителя),
     NPZ_CHANNEL (канал), NPZ_BOT_SUBS (subscribers.json бота, необязательно)
Запуск: python3 channel_report.py [--dry] [--selftest] [--reset-baseline]
"""
import os, sys, json, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetAdminLogRequest, GetFullChannelRequest
from telethon.tl.types import ChannelAdminLogEventsFilter
from telethon.tl.types import (ChannelAdminLogEventActionParticipantJoin,
                               ChannelAdminLogEventActionParticipantJoinByInvite,
                               ChannelAdminLogEventActionParticipantLeave)

SESSION = os.environ.get("NPZ_TG_SESSION", "/root/tg-recon/instances/nolan/session.txt")
CHANNEL = os.environ.get("NPZ_CHANNEL", "@npz_karta_online")
CHAT = os.environ.get("NPZ_REPORT_CHAT", "609952529")
TOKEN_FILE = os.environ.get("NPZ_REPORT_TOKEN", "/root/.npz-bot/token")
BOT_SUBS = os.environ.get("NPZ_BOT_SUBS", "/root/.npz-bot-bpl/subscribers.json")
STATE = os.environ.get("NPZ_CHANNEL_STATE", "/root/.npz-bot/channel-report-state.json")

JOIN = (ChannelAdminLogEventActionParticipantJoin,
        ChannelAdminLogEventActionParticipantJoinByInvite)
LEAVE = (ChannelAdminLogEventActionParticipantLeave,)


def classify(events, last_id, newcomers):
    """events — журнал (порядок любой). Считаем только события новее last_id.
    Возвращает (пришло, ушло_новых, отвал_базы, max_id, набор новичков)."""
    fresh = [e for e in events if e.id > last_id]
    joined = left_new = left_base = 0
    for e in sorted(fresh, key=lambda e: e.id):      # по возрастанию: вход раньше выхода
        uid = str(e.user_id)
        if isinstance(e.action, JOIN):
            joined += 1
            newcomers[uid] = e.date.strftime("%Y-%m-%d")
        elif isinstance(e.action, LEAVE):
            if uid in newcomers:
                del newcomers[uid]
                left_new += 1
            else:
                left_base += 1
    return joined, left_new, left_base, max([e.id for e in fresh], default=last_id), newcomers


def load_state():
    try:
        with open(STATE) as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("last_event_id", 0)
    s.setdefault("newcomers", {})
    s.setdefault("total_joined", 0)
    s.setdefault("baseline_at", None)
    s.setdefault("baseline_total", None)
    return s


def read_log(state):
    c = TelegramClient(StringSession(open(SESSION).read()), 2040,
                       "b18441a1ff607e10a989891a5462e627")
    c.connect()
    ch = c.get_entity(CHANNEL)
    total = c(GetFullChannelRequest(ch)).full_chat.participants_count
    flt = ChannelAdminLogEventsFilter(join=True, leave=True)

    events, max_id = [], 0
    for _ in range(20):        # ponytail: 20 страниц по 100 — потолок от бесконечного цикла
        res = c(GetAdminLogRequest(channel=ch, q="", max_id=max_id, min_id=0,
                                   limit=100, events_filter=flt, admins=[]))
        if not res.events:
            break
        events.extend(res.events)
        max_id = res.events[-1].id
        if max_id <= state["last_event_id"]:
            break              # дошли до уже разобранного — глубже не нужно
    c.disconnect()
    return total, events


def bot_subs():
    try:
        with open(BOT_SUBS) as f:
            subs = json.load(f)["subscribers"]
        return sum(1 for v in subs.values() if v.get("status") == "active")
    except Exception:
        return None


def send(text):
    token = open(TOKEN_FILE).read().strip()
    data = urllib.parse.urlencode({"chat_id": CHAT, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("ok", False)


def selftest():
    class Ev:
        def __init__(self, i, action, uid):
            self.id, self.action, self.user_id = i, action, uid
            self.date = datetime.now(timezone.utc)

    j = ChannelAdminLogEventActionParticipantJoin()
    lv = ChannelAdminLogEventActionParticipantLeave()

    # новичок пришёл и ушёл — это потеря живого, а не отвал накрутки
    assert classify([Ev(2, lv, 77), Ev(1, j, 77)], 0, {})[:3] == (1, 1, 0)

    # ушёл тот, кого мы не видели приходящим → это база (накрутка)
    assert classify([Ev(3, lv, 55)], 0, {})[:3] == (0, 0, 1)

    # уже разобранные события не считаются повторно
    assert classify([Ev(5, j, 9), Ev(4, j, 8)], 5, {})[:3] == (0, 0, 0)

    # новичок прошлого прогона, ушедший сегодня, всё ещё считается новым
    r = classify([Ev(9, lv, 42)], 8, {"42": "2026-08-01"})
    assert r[:3] == (0, 1, 0) and "42" not in r[4]

    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0

    dry = "--dry" in sys.argv
    reset = "--reset-baseline" in sys.argv
    state = load_state()
    first = state["baseline_at"] is None or reset
    total, events = read_log(state)

    if first:
        # Базовая отметка: всё, что в канале сейчас, считаем накруткой. Новым будет только
        # то, что придёт после этого прогона.
        state.update(baseline_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                     baseline_total=total, newcomers={}, total_joined=0,
                     last_event_id=max([e.id for e in events], default=0))
        lines = ["📊 %s — отсчёт пошёл" % CHANNEL,
                 "👥 в канале сейчас: %d — это базовая отметка" % total,
                 "Дальше считаю только тех, кто придёт после неё."]
    else:
        j, ln, lb, last, newcomers = classify(events, state["last_event_id"],
                                              dict(state["newcomers"]))
        state.update(last_event_id=last, newcomers=newcomers,
                     total_joined=state["total_joined"] + j)
        lines = ["📊 %s — за сутки" % CHANNEL,
                 "➕ новых: %d" % j,
                 "➖ ушло новых: %d" % ln,
                 "♻️ отвал накрутки: %d" % lb,
                 "",
                 "📈 новых с %s: %d, осталось %d" % (
                     state["baseline_at"], state["total_joined"], len(newcomers)),
                 "👥 в канале: %d" % total]

    n = bot_subs()
    if n is not None:
        lines.append("🤖 подписчиков бота: %d" % n)
    lines.append(datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m %H:%M МСК"))
    text = "\n".join(lines)

    if dry:
        print(text)
        print("\n[dry] состояние не сохранено; last_event_id=%s" % state["last_event_id"])
        return 0
    if not send(text):
        print("отправка не удалась — состояние не двигаю")
        return 1
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(state, f, ensure_ascii=False)
    print("отправлено:", text.replace("\n", " · "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
