#!/usr/bin/env python3
"""Группировка по времени события + отсечка по свежести в strike_alerts.py.

Инцидент 09.08.2026: сбойный прогон накопил бэклог, а когда прошёл — разослал
11 старых ударов (28.07-01.08) отдельными сообщениями подряд ("спам-молнии").
Причины: (1) никакой группировки — for-цикл слал по сообщению на удар;
(2) никакой отсечки по свежести — молния про "сейчас" ушла про прошлый месяц.

Запуск: python3 test_strike_alerts_batch.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strike_alerts import build_strike_notifications, group_notices_for_send, MAX_AGE_HOURS

NOW = datetime.datetime(2026, 8, 9, 12, 0, tzinfo=datetime.timezone.utc)
SUB_ALL = {"s": {"status": "active", "alerts": {"enabled": True, "regions": ["all"], "attacks": True}}}


def strike(sid, date, time_):
    return {"id": sid, "date": date, "time": time_, "city": "Город-%s" % sid,
            "region": "область", "type": "drone", "target": "объект"}


# 1) 4 удара в пределах 2 часов -> 1 сообщение
strikes_close = [
    strike("a", "2026-08-09", "08:00"),
    strike("b", "2026-08-09", "09:00"),
    strike("c", "2026-08-09", "09:30"),
    strike("d", "2026-08-09", "09:50"),
]
notices, new_seen = build_strike_notifications(strikes_close, SUB_ALL, seen=[],
                                                max_age_hours=MAX_AGE_HOURS, now=NOW)
grouped = group_notices_for_send(notices)
assert len(notices) == 4, notices
assert len(grouped) == 1, grouped
assert set(grouped[0]["strike_ids"]) == {"a", "b", "c", "d"}
assert "Удары БПЛА (4)" in grouped[0]["text"], grouped[0]["text"]
assert new_seen == {"a", "b", "c", "d"}
print("ok: 4 удара в пределах 2ч -> 1 сообщение")

# 1a) сгруппированное сообщение КОМПАКТНОЕ: одна шапка, одна ссылка, строка на удар.
# Склейка четырёх готовых карточек подряд формально «одно сообщение», но читается
# как та же пачка — ради этого фикс и делался.
text = grouped[0]["text"]
assert text.count("/radar.html") == 1, text
assert text.count("💥") == 1, text
for city in ("Город-a", "Город-b", "Город-c", "Город-d"):
    assert city in text, text
print("ok: сгруппированное сообщение компактное (1 шапка, 1 ссылка, 4 строки)")

# 2) удары с разрывом 3 часа -> 2 сообщения
strikes_gap = [
    strike("e", "2026-08-09", "06:00"),
    strike("f", "2026-08-09", "09:00"),  # разрыв с предыдущим = 3ч > GROUP_GAP_HOURS
]
notices, new_seen = build_strike_notifications(strikes_gap, SUB_ALL, seen=[],
                                                max_age_hours=MAX_AGE_HOURS, now=NOW)
grouped = group_notices_for_send(notices)
assert len(grouped) == 2, grouped
assert [g["strike_ids"] for g in grouped] == [["e"], ["f"]], grouped
print("ok: разрыв 3ч -> 2 сообщения")

# 3) удар возрастом 5 суток -> 0 сообщений, но помечен seen
strikes_old = [strike("old", "2026-08-04", "12:00")]
notices, new_seen = build_strike_notifications(strikes_old, SUB_ALL, seen=[],
                                                max_age_hours=MAX_AGE_HOURS, now=NOW)
assert notices == [], notices
assert new_seen == {"old"}, new_seen
print("ok: удар 5 суток -> 0 сообщений, но seen")


# 4) re-seed guard: состояние отстало от архива -> 0 отправок, всё помечено seen.
# Ровно сценарий 09.08.2026: seen=9 при 365 ударах и 26 живых подписчиках.
import json
import tempfile

import strike_alerts as SA

sent_texts = []
tmp = tempfile.mkdtemp()
archive = [strike(str(i), "2026-08-09", "08:00") for i in range(50)]
orig = (SA.STRIKES_PATH, SA.SUBS_PATH, SA.STATE_PATH, SA.send_message)
try:
    SA.STRIKES_PATH = os.path.join(tmp, "strikes.json")
    SA.SUBS_PATH = os.path.join(tmp, "subscribers.json")
    SA.STATE_PATH = os.path.join(tmp, "state.json")
    SA.send_message = lambda *a, **k: sent_texts.append(a) or {"ok": True}
    json.dump({"strikes": archive}, open(SA.STRIKES_PATH, "w"))
    json.dump({"subscribers": SUB_ALL}, open(SA.SUBS_PATH, "w"))
    json.dump({"seen": ["0"]}, open(SA.STATE_PATH, "w"))  # отстал на 49 ударов
    sys.argv = ["strike_alerts.py", "--send"]
    SA.main()
    assert sent_texts == [], sent_texts
    assert len(json.load(open(SA.STATE_PATH))["seen"]) == 50
finally:
    (SA.STRIKES_PATH, SA.SUBS_PATH, SA.STATE_PATH, SA.send_message) = orig
print("ok: состояние отстало от архива -> re-seed без рассылки")

print("\nAll strike_alerts_batch tests passed.")
