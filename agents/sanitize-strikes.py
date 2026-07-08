#!/usr/bin/env python3
"""
sanitize-strikes.py — детерминированный фильтр качества для data/strikes.json.

Вырезает записи, которые НЕ должны попадать на нейтральную OSINT-карту:
  • украиноязычный текст (вербатим-репосты укр. Telegram-каналов) — буквы іїєґ;
  • пропаганда/партийная лексика ("Слава Україні", "Повітряні Сили", "терориста" и т.п.);
  • невалидный confidence (только confirmed|reported|rumored);
  • офф-топик про сбитые самолёты/лётчиков без связи с НПЗ/топливом
    (сайт — про топливную инфраструктуру, не про воздушные бои);
  • свалки воздушных тревог без объекта (city пустой/"Неизвестно" И target «неуточнённый»).

Вызывается pre-commit хуком (см. .githooks/pre-commit) — так что ни один коллектор
(newswatch, ручной, внешняя модель) не может опубликовать такое. Идемпотентен, exit 0.

Запуск:  python3 agents/sanitize-strikes.py [путь]   (по умолчанию data/strikes.json)
"""
import json
import sys

UA_CHARS = set("іїєґ")
UA_MARK = ["Повітр", "Слава Україн", "Гарні новини", "терориста", "Далі буде",
           "відмінусували", "Дякуємо", "ворожий", "збитий в бою", "Твір на тему",
           "ЗСУ переможе", "русн", "орки", "кацап", "москаль"]
VALID_CONF = {"confirmed", "reported", "rumored"}
JET_WORDS = ["су-3", "су-5", "миг-", "истребител", "льотчик", "лётчик", "самолёт", "самолет"]
FUEL_WORDS = ["нпз", "нефт", "топлив", "нефтебаз", "терминал", "азс", "гпз", "энергет",
              "подстанц", "тэц", "тэс", "грэс", "нпс", "нефтехим"]


def reason_bad(x):
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


def sanitize(path):
    s = json.load(open(path, encoding="utf-8"))
    arr = s if isinstance(s, list) else s.get("strikes", [])
    keep, removed = [], []
    for x in arr:
        r = reason_bad(x)
        (removed if r else keep).append((x, r))
    if not removed:
        return 0
    for x, r in removed:
        sys.stderr.write("  sanitize: drop %s | %s | %s\n"
                         % (x.get("date"), str(x.get("city"))[:24], r))
    newarr = [x for x, _ in keep]
    if isinstance(s, list):
        s = newarr
    else:
        s["strikes"] = newarr
    json.dump(s, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return len(removed)


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "data/strikes.json"
    try:
        n = sanitize(p)
        if n:
            sys.stderr.write("sanitize-strikes: удалено %d мусорных записей из %s\n" % (n, p))
    except FileNotFoundError:
        pass
    except Exception as e:  # никогда не блокируем коммит из-за самого санитайзера
        sys.stderr.write("sanitize-strikes: warn %s\n" % e)
    sys.exit(0)


def demo():
    """assert-самопроверка: пропаганда/офф-топик/битый conf режутся, нормальное остаётся."""
    good = {"date": "2026-07-08", "city": "Рязань", "target": "Рязанский НПЗ",
            "confidence": "reported", "title": "Удар по НПЗ"}
    cases = [
        ({"city": "X", "target": "Слава Україні", "confidence": "reported"}, "UA-lang"),
        ({"city": "X", "target": "прилёт по кацапам", "confidence": "reported"}, "propaganda"),
        ({"city": "X", "target": "сбит Су-35", "confidence": "reported"}, "offtopic-aircraft"),
        ({"city": "X", "target": "сбит Су-35 у НПЗ", "confidence": "reported"}, None),  # есть fuel-контекст
        ({"city": "X", "target": "НПЗ горит", "confidence": "сообщено"}, "bad-confidence:сообщено"),
        ({"city": "Неизвестно", "target": "неуточнённый объект", "confidence": "reported"}, "empty-alert"),
        (good, None),
    ]
    for x, exp in cases:
        got = reason_bad(x)
        assert got == exp, "reason_bad(%s) = %r, ожидалось %r" % (x, got, exp)
    print("demo OK")
