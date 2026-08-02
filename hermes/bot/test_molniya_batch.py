#!/usr/bin/env python3
"""Удары одного прогона уходят ОДНИМ сообщением, а не пачкой молний в одну минуту.

Сборщик ходит раз в 20 минут, поэтому «одновременные» молнии — это не четыре удара
в одну минуту, а один заход детектора. Запуск: python3 test_molniya_batch.py
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_CHANNEL_MIRRORS", "@test_mirror")

import radar_publish as RP
import day_state as DS
import render as R


def strike(city, target, date="2026-08-02"):
    return {"date": date, "time": "04:00", "city": city, "region": city + "ская область",
            "target": target, "detail": "Подробности по " + city, "confidence": "reported"}


def run(items):
    """Публикует пачку на подменённой отправке; возвращает (результат, тексты сообщений)."""
    texts = []
    orig = (RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state)
    RP.api_call = lambda method, **kw: (texts.append(kw.get("text")) or
                                        {"ok": True, "result": {"message_id": len(texts)}})
    RP._get_active_subscribers = lambda: []
    state = DS.ensure_today(None, DS.today_iso())
    DS.load_state = lambda: state
    DS.save_state = lambda s: None
    try:
        return RP.publish_strikes_batch(items), texts
    finally:
        (RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state) = orig


# четыре удара одного прогона → одно сообщение в канал (+ по одному в каждое зеркало)
res, texts = run([(strike("Уфа", "НПЗ"), ""), (strike("Саратов", "жилой дом"), ""),
                  (strike("Самара", "логистический центр"), ""), (strike("Сызрань", "НПЗ"), "")])
уникальных = set(texts)
assert res["published"] == 4, res
assert len(уникальных) == 1, "разные тексты в канал и зеркало: %d" % len(уникальных)
body = texts[0]
assert "МОЛНИЯ · 4 удара" in body, body
for city in ("Уфа", "Саратов", "Самара", "Сызрань"):
    assert city in body, "город %s потерян: %s" % (city, body)
assert body.count("МОЛНИЯ") == 1, "заголовок продублирован: " + body

# один удар — прежний одиночный формат, без «N ударов»
res, texts = run([(strike("Рязань", "НПЗ"), "")])
assert res["published"] == 1, res
assert "удара" not in texts[0].split("\n")[0], texts[0].split("\n")[0]

# 🔴 склонение: 1 удар / 2 удара / 5 ударов — иначе в заголовке «5 удара»
assert R._udarov(1) == "удар" and R._udarov(2) == "удара" and R._udarov(5) == "ударов"
assert R._udarov(11) == "ударов" and R._udarov(21) == "удар", "11 и 21 — особые случаи"

# длинный список сворачивается, а не режется молча посреди строки
many = [(strike("Город%d" % i, "объект"), "") for i in range(9)]
res, texts = run(many)
assert "и ещё 3 на карте" in texts[0], texts[0]

# описание не печатается дважды, когда why и context — один и тот же текст
one = R.render_molniya({"headline": "Удар по НПЗ", "city": "Уфа", "region": "Башкортостан",
                        "target": "НПЗ", "why": "Пожар в резервуарном парке",
                        "context": "Пожар в резервуарном парке", "confidence": "reported"})
assert one.count("Пожар в резервуарном парке") == 1, one

print("test_molniya_batch: ok")
