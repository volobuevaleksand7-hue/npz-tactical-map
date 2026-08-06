#!/usr/bin/env python3
"""Отсутствие события не может быть молнией.

04.08.2026 в @NPZmap ушли посты «🚨 МОЛНИЯ · Новых ударов по нефтегазовой
инфраструктуре не зафиксировано за последний час» с пустыми полями «📍 — , — 🎯 —».
Сборщик оформил часовой отчёт «ничего не произошло» как удар, классификатор увидел
слово «нефтегазовой» и выдал TIER-1. Запуск: python3 test_molniya_no_event.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_CHANNEL_MIRRORS", "")

import radar_publish as RP
import day_state as DS

NOTHING = {"date": "2026-08-04", "time": "23:08", "city": "", "region": "", "target": "",
           "title": "Новых ударов по нефтегазовой инфраструктуре не зафиксировано за последний час",
           "detail": "", "confidence": "reported"}
REPORT = dict(NOTHING, title="Отчет за последний час", city="Москва", target="нефтебаза")
BLANK = {"date": "2026-08-04", "city": "—", "region": "—", "target": "—", "title": "—",
         "confidence": "reported"}
REAL = {"date": "2026-08-04", "time": "04:00", "city": "Саратов", "region": "Саратовская область",
        "target": "нефтеперерабатывающий завод", "detail": "Пожар на установке",
        "confidence": "reported"}


def sent(strike_or_items, batch=False):
    """Считает, сколько сообщений реально ушло бы в канал."""
    calls = []
    orig = (RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state)
    RP.api_call = lambda method, **kw: (calls.append(kw.get("text")) or
                                        {"ok": True, "result": {"message_id": len(calls)}})
    RP._get_active_subscribers = lambda: []
    state = DS.ensure_today(None, DS.today_iso())
    DS.load_state = lambda: state
    DS.save_state = lambda s: None
    try:
        if batch:
            RP.publish_strikes_batch([(s, "") for s in strike_or_items])
        else:
            RP.publish_strike_molniya(dict(strike_or_items))
    finally:
        (RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state) = orig
    return calls


# 🔴 главное: «ничего не произошло» не уходит в канал ни одним из путей
for bad, name in ((NOTHING, "нет ударов"), (REPORT, "отчёт за час"), (BLANK, "пустая карточка")):
    assert RP.refuse_reason(bad), "не распознан отказ: " + name
    assert sent(bad) == [], "🔴 в канал ушла пустая молния (%s)" % name

# реальный удар по-прежнему публикуется
assert RP.refuse_reason(REAL) is None
out = sent(REAL)
assert out and "Саратов" in out[0], out

# в пачке пустышки отсеиваются, реальные остаются
out = sent([NOTHING, REAL, BLANK], batch=True)
assert len(out) == 1 and "Саратов" in out[0], out
assert "не зафиксировано" not in out[0], out

# пачка из одних пустышек не шлёт вообще ничего
assert sent([NOTHING, BLANK], batch=True) == []

print("test_molniya_no_event: ok")
