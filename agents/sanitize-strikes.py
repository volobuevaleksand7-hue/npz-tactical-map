#!/usr/bin/env python3
"""
sanitize-strikes.py — детерминированный фильтр качества для data/strikes.json.

Словарь и правила живут в agents/neutrality.py (единственная копия — до 22.07
их было две, и они разъехались). Здесь остаётся только работа с файлом:
пройти по массиву записей, эпитеты вычистить, непубликуемое удалить.

  • scrub  (чиним)   — оценочные эпитеты режутся, запись остаётся;
  • drop   (удаляем) — укр. язык, лозунг, призыв, битый confidence,
                       офф-топик про сбитые самолёты, пустая воздушная тревога.

Вызывается pre-commit хуком (см. .githooks/pre-commit) — так что ни один
коллектор (newswatch, ручной, внешняя модель) не может опубликовать такое.
Идемпотентен, exit 0 всегда: санитайзер не имеет права заблокировать коммит.

Запуск:  python3 agents/sanitize-strikes.py [путь]   (по умолчанию data/strikes.json)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import neutrality  # noqa: E402

# Имена оставлены для обратной совместимости: на них ссылались внешние скрипты.
scrub = neutrality.scrub_record
reason_bad = neutrality.reason_bad

TEXT_FIELDS = ("target", "title", "detail", "city", "region")


def translit_warnings(x):
    """Битая транслитерация, которую словарь LATIN_FIX не смог починить сам.

    Две разные приметы, обе — брак коллектора, а не стиль источника:
      • слово с кириллицей и латиницей вперемешку («Гидросталькonstruktsiya»);
      • латиница в city/region — русский населённый пункт латиницей («Yalta»,
        «Novospasskoye») не пишет ни один русскоязычный источник. В target такое
        не проверяем: там латиницей законно стоят суда и бренды.

    Не удаляем и не блокируем: правильное русское написание известно источнику, а
    не нам, угадать = подделать; а падение хука заморозило бы публикацию у крона
    (инцидент 29.07). Задача — чтобы такая запись была видна в логе коммита.
    """
    out = []
    blob = " ".join(str(x.get(f) or "") for f in TEXT_FIELDS)
    out += neutrality.mixed_script_words(blob)
    for f in ("city", "region"):
        out += neutrality.latin_leftovers(x.get(f))
    return sorted(set(out))


def sanitize(path):
    """Чистит массив записей под ключом strikes/history (или сам список). Возвращает N удалённых."""
    s = json.load(open(path, encoding="utf-8"))
    if isinstance(s, list):
        keys = [None]
    else:
        keys = [k for k in ("strikes", "history") if isinstance(s.get(k), list)]
    total = 0
    scrubbed = 0
    for k in keys:
        arr = s if k is None else s[k]
        keep, removed = [], []
        for x in arr:
            if isinstance(x, dict) and scrub(x):
                scrubbed += 1
                sys.stderr.write("  sanitize: scrub эпитетов | %s | %s\n"
                                 % (x.get("date"), str(x.get("city"))[:24]))
            if isinstance(x, dict):
                bad_translit = translit_warnings(x)
                if bad_translit:
                    sys.stderr.write("  sanitize: битая транслитерация %s | %s | %s "
                                     "— впиши имя в LATIN_FIX (agents/neutrality.py)\n"
                                     % (", ".join(bad_translit), x.get("date"),
                                        str(x.get("city"))[:24]))
            r = reason_bad(x) if isinstance(x, dict) else None
            (removed if r else keep).append(x)
            if r:
                sys.stderr.write("  sanitize: drop %s | %s | %s\n"
                                 % (x.get("date"), str(x.get("city"))[:24], r))
        if removed:
            total += len(removed)
            if k is None:
                s = keep
            else:
                s[k] = keep
    if total or scrubbed:
        json.dump(s, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return total


def demo():
    """assert-самопроверка. Словарные кейсы — в neutrality.demo(); здесь работа с файлом."""
    import tempfile
    neutrality.demo()
    p = os.path.join(tempfile.mkdtemp(), "s.json")
    json.dump({"strikes": [
        {"date": "2026-07-08", "city": "Рязань", "target": "Рязанский НПЗ", "confidence": "reported"},
        {"date": "2026-07-08", "city": "Севастополь", "target": "порт",
         "detail": "Удар по оккупированному порту", "confidence": "reported"},
        {"date": "2026-07-08", "city": "X", "target": "Слава Україні", "confidence": "reported"},
    ]}, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    assert sanitize(p) == 1
    out = json.load(open(p, encoding="utf-8"))["strikes"]
    assert len(out) == 2
    assert out[1]["detail"] == "Удар по порту", out[1]
    assert sanitize(p) == 0, "санитайзер не идемпотентен"

    # 🔴 28.07 -> 09.08: полутранслит «завод ZAO «Гидросталькonstruktsiya»» лежал в
    # архиве 12 дней. Знакомое имя чинит словарь, незнакомое обязано попасть в лог.
    assert translit_warnings({"target": "завод ZAO «Гидросталькonstruktsiya»"}) == []
    assert translit_warnings({"target": "завод «Уралхимmash»"}) == ["Уралхимmash"]
    assert translit_warnings({"city": "Novospasskoye"}) == [], "знакомое чинится словарём"
    assert translit_warnings({"city": "Kotelnikovo"}) == ["Kotelnikovo"]
    # латиница в target — норма (суда, бренды), в отличие от city/region
    assert translit_warnings({"city": "Чёрное море", "target": "танкер Nordic Zenith"}) == []
    print("sanitize-strikes demo OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv or "--demo" in sys.argv:
        demo()
        sys.exit(0)
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
