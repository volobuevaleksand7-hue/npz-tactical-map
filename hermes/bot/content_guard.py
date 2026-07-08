#!/usr/bin/env python3
"""
content_guard.py — нейтральность на этапе ПУБЛИКАЦИИ (Telegram + сайт).

Санитайзер agents/sanitize-strikes.py вырезает мусор из data/strikes.json в
pre-commit хуке — но это происходит на git-commit, ПОЗЖЕ отправки молнии в канал.
Этот модуль даёт тот же фильтр как импортируемую функцию, чтобы вызывать его
ПЕРЕД публикацией/рендером (strike_pipeline, radar_publish, broadcast,
editorial_digest, gen-news) — тогда пропаганда/укр-вербатим/офф-топик не уйдёт
подписчикам, даже если запись ещё не прошла санитайзер.

⚠️ Логика reason_bad должна совпадать с agents/sanitize-strikes.py. Меняешь одно —
поправь второе (или вынеси в общий модуль).
"""

UA_CHARS = set("іїєґ")
UA_MARK = ["Повітр", "Слава Україн", "Гарні новини", "терориста", "Далі буде",
           "відмінусували", "Дякуємо", "ворожий", "збитий в бою", "Твір на тему",
           "ЗСУ переможе", "русня", "орки", "кацап", "москаль"]
VALID_CONF = {"confirmed", "reported", "rumored"}
JET_WORDS = ["су-3", "су-5", "миг-", "истребител", "льотчик", "лётчик", "самолёт", "самолет"]
FUEL_WORDS = ["нпз", "нефт", "топлив", "нефтебаз", "терминал", "азс", "гпз", "энергет",
              "подстанц", "тэц", "тэс", "грэс", "нпс", "нефтехим"]


def reason_bad(x):
    """Возвращает строку-причину, если запись НЕ должна публиковаться, иначе None."""
    import json
    blob = json.dumps(x, ensure_ascii=False)
    if any(c in blob for c in UA_CHARS):
        return "UA-lang"
    if any(m in blob for m in UA_MARK):
        return "propaganda"
    if x.get("confidence") not in VALID_CONF:
        return "bad-confidence:%s" % x.get("confidence")
    tgt = (str(x.get("target", "")) + " " + str(x.get("title", ""))).lower()
    if any(k in tgt for k in JET_WORDS) and not any(k in tgt for k in FUEL_WORDS):
        return "offtopic-aircraft"
    city = str(x.get("city", "")).strip().lower()
    if city in ("", "неизвестно") and "неуточ" in tgt:
        return "empty-alert"
    return None


def is_clean(x):
    """True, если запись можно публиковать (нейтральна и по теме)."""
    return reason_bad(x) is None


def demo():
    assert is_clean({"city": "Рязань", "target": "Рязанский НПЗ", "confidence": "reported"})
    assert not is_clean({"city": "X", "target": "Слава Україні", "confidence": "reported"})
    assert not is_clean({"city": "X", "target": "сбит Су-35", "confidence": "reported"})
    assert is_clean({"city": "X", "target": "сбит Су-35 у НПЗ", "confidence": "reported"})
    assert not is_clean({"city": "X", "target": "НПЗ", "confidence": "сообщено"})
    print("content_guard demo OK")


if __name__ == "__main__":
    demo()
