#!/usr/bin/env python3
"""Ежедневный отчёт по каналу владельцу: сколько пришло, сколько ушло, сколько всего.

Bot API даёт только итоговое число участников — при 5 пришедших и 5 ушедших дельта равна
нулю и отчёт врёт. Поэтому приход/уход берём из журнала действий канала (админ-лог) через
юзербота-создателя; Telegram хранит журнал ~48 часов, суточного прогона хватает.

ponytail: без БД — итог прошлого прогона лежит в одном текстовом файле рядом с состоянием.

env: NPZ_REPORT_CHAT (кому), NPZ_REPORT_TOKEN (файл токена бота-отправителя),
     NPZ_CHANNEL (канал), NPZ_BOT_SUBS (subscribers.json бота, необязательно)
Запуск: python3 channel_report.py [--dry]
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
STATE = os.environ.get("NPZ_CHANNEL_STATE", "/root/.npz-bot/channel-report-last.json")
DRY = "--dry" in sys.argv

JOIN = (ChannelAdminLogEventActionParticipantJoin,
        ChannelAdminLogEventActionParticipantJoinByInvite)
LEAVE = (ChannelAdminLogEventActionParticipantLeave,)


def tally(pages, since):
    """Считает приход/уход по страницам журнала (свежие сначала), пока не упрётся в границу.
    🔴 Telegram отдаёт максимум 100 событий за запрос — в шумные сутки одной страницы мало,
    поэтому счёт вынесен сюда и покрыт --selftest."""
    joined = left = seen = 0
    for page in pages:
        if not page:
            break
        stop = False
        for ev in page:
            seen += 1
            if ev.date < since:
                stop = True
                continue
            if isinstance(ev.action, JOIN):
                joined += 1
            elif isinstance(ev.action, LEAVE):
                left += 1
        if stop:
            break
    return joined, left, seen


def collect():
    c = TelegramClient(StringSession(open(SESSION).read()), 2040,
                       "b18441a1ff607e10a989891a5462e627")
    c.connect()
    ch = c.get_entity(CHANNEL)
    total = c(GetFullChannelRequest(ch)).full_chat.participants_count
    flt = ChannelAdminLogEventsFilter(join=True, leave=True)

    def pages():
        max_id = 0
        for _ in range(20):  # ponytail: 20 страниц = 2000 событий, потолок от бесконечного цикла
            res = c(GetAdminLogRequest(channel=ch, q="", max_id=max_id, min_id=0,
                                       limit=100, events_filter=flt, admins=[]))
            if not res.events:
                return
            yield res.events
            max_id = res.events[-1].id

    joined, left, seen = tally(pages(), datetime.now(timezone.utc) - timedelta(hours=24))
    c.disconnect()
    return total, joined, left, seen


def bot_subs():
    try:
        with open(BOT_SUBS) as f:
            subs = json.load(f)["subscribers"]
        return sum(1 for v in subs.values() if v.get("status") == "active")
    except Exception:
        return None


def prev_total():
    try:
        with open(STATE) as f:
            return json.load(f).get("total")
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
    """Проверяет ровно то, что легко сломать: счёт через границу страниц и отсечку по времени."""
    now = datetime.now(timezone.utc)

    class Ev:
        def __init__(self, action, hours_ago):
            self.action = action
            self.date = now - timedelta(hours=hours_ago)

    j = ChannelAdminLogEventActionParticipantJoin()
    lv = ChannelAdminLogEventActionParticipantLeave()
    since = now - timedelta(hours=24)

    # две полные страницы: приход считается на обеих, значит пагинация не теряет вторую
    assert tally([[Ev(j, 1)] * 100, [Ev(j, 2)] * 100], since)[0] == 200

    # событие старше суток обрывает счёт и само не считается
    joined, left, _ = tally([[Ev(j, 1), Ev(lv, 2), Ev(j, 30)], [Ev(j, 40)] * 100], since)
    assert (joined, left) == (1, 1), (joined, left)

    # пустая страница не роняет и не зацикливает
    assert tally([[]], since) == (0, 0, 0)
    print("selftest ok")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0
    total, joined, left, log_seen = collect()
    prev = prev_total()
    net = "" if prev is None else " (%+d за сутки)" % (total - prev)

    lines = ["📊 %s — за сутки" % CHANNEL,
             "➕ пришло: %d" % joined,
             "➖ ушло: %d" % left,
             "👥 всего: %d%s" % (total, net)]
    if log_seen == 0:
        lines.append("⚠️ журнал канала пуст — приход/уход мог не записаться")
    n = bot_subs()
    if n is not None:
        lines.append("🤖 подписчиков бота: %d" % n)
    lines.append(datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m %H:%M МСК"))
    text = "\n".join(lines)

    if DRY:
        print(text)
        print("\n[dry] событий в журнале: %d, прошлый итог: %s" % (log_seen, prev))
        return 0
    if not send(text):
        print("отправка не удалась — водяной знак не двигаю")
        return 1
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump({"total": total, "at": datetime.now(timezone.utc).isoformat()}, f)
    print("отправлено:", text.replace("\n", " · "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
