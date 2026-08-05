#!/usr/bin/env python3
"""Число поражённых складов Wildberries на двух РУКОПИСНЫХ страницах — из data/warehouses.json.

udar-po-skladu-ozon.html и ceny-marketpleysy-posle-udarov.html не генерируются
скриптом (как /skolko-skladov-wildberries-ozon через gen-warehouses-page.py) — это
ручной HTML со счётчиком, вбитым в текст. 01.08 счётчик уже правили руками (17→19),
и он снова разошёлся с данными за 4 дня. Здесь синхронизируется ТОЛЬКО число —
остальной текст страниц остаётся ручным.

Каждое вхождение найдено по своему regex-якорю (окружающий литеральный текст, без
самой цифры) — не глобальная замена "19"→"21": на странице уже есть даты вроде
"31 июля", и слепая замена по значению рано или поздно испортит дату, совпавшую со
счётчиком.

🔴 Часть якорей ("N объектов" и т.п.) требуют русского склонения по числительному —
"19 объектов", но "21 объект", "22 объекта". Просто воткнуть цифру недостаточно:
на 21 склад слепая подстановка дала бы "21 объектов" (неверно). ru_count() — тот же
one/few/many, что в стандартных таблицах множественных форм CLDR/ICU для ru (без
более тонкого учёта падежа — этого различия сайты с цифрами в тексте обычно не
делают, и это осознанное упрощение).

Новая страница/фраза с этим же числом → добавь свой якорь в PATTERNS/DECLINED.

Запуск (пишет файлы):     python3 agents/sync-warehouse-counts.py
Проверка без записи:      python3 agents/sync-warehouse-counts.py --check
Самопроверка (assert):    python3 agents/sync-warehouse-counts.py --demo
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WH_SRC = os.path.join(ROOT, "data", "warehouses.json")


def ru_count(n, one, few, many):
    """Числительное + сущ. как ПОДЛЕЖАЩЕЕ/именительный ряд: 21 объект, 22 объекта, 25 объектов."""
    n100 = n % 100
    n10 = n % 10
    if 11 <= n100 <= 14:
        return many
    if n10 == 1:
        return one
    if 2 <= n10 <= 4:
        return few
    return many


def ru_count_gen(n, one, many):
    """Числительное + сущ. в позиции, где всю фразу склоняет предлог/глагол (родительный
    падеж — «помимо», «недостаточно»): только форма на 1 отличается от прочих."""
    n100 = n % 100
    n10 = n % 10
    if n10 == 1 and n100 != 11:
        return one
    return many


# --- якоря без склонения: после числа сразу нелитеральный текст без сущ. (эллипсис/лейбл) ---
# (файл, [regex с ОДНОЙ группой \d+ в стабильном литеральном контексте])
PLAIN = {
    "udar-po-skladu-ozon.html": [
        r'(объектов против )\d+( — три проверяемые причины)',
        r'(объектов против )\d+(</strong> у Wildberries)',
        r'(<div class="val">)\d+(</div><div class="lbl">поражённых складов Wildberries</div>)',
        r'(таких объектов уже )\d+(\.)',
    ],
    "ceny-marketpleysy-posle-udarov.html": [
        r'(<div class="val">)\d+(</div><div class="lbl">поражённых складов Wildberries</div>)',
    ],
}

# --- якоря со склонением: (regex с prefix/suffix группами + альтернативой из трёх форм,
#     функция согласования, формы one/few/many) ---
DECLINED = {
    "udar-po-skladu-ozon.html": [
        (r'(поражено уже )\d+ (объект|объекта|объектов)(\.)',
         ru_count, ("объект", "объекта", "объектов")),
        (r'(закономерность\.</strong> )\d+ (поражённый объект|поражённых объекта|поражённых объектов)( — выборка)',
         ru_count, ("поражённый объект", "поражённых объекта", "поражённых объектов")),
        (r'(Помимо )\d+ (объекта|объектов)( Wildberries)',
         ru_count_gen, ("объекта", "объектов")),
        (r'(выборки — )\d+ (поражённого объекта|поражённых объектов)( недостаточно)',
         ru_count_gen, ("поражённого объекта", "поражённых объектов")),
    ],
    "ceny-marketpleysy-posle-udarov.html": [
        (r'(поражено <strong>)\d+ (складской объект|складских объекта|складских объектов)( Wildberries</strong>)',
         ru_count, ("складской объект", "складских объекта", "складских объектов")),
    ],
}


def wb_hit_count():
    with open(WH_SRC, encoding="utf8") as f:
        doc = json.load(f)
    return sum(1 for w in doc["warehouses"] if w["status"] == "hit" and w["operator"] == "wb")


def apply_patterns(text, count):
    """Возвращает (новый_текст, [(pattern, число_замен), ...])."""
    hits = []
    for pat in PLAIN.get(_current_file, []):
        text, k = re.subn(pat, lambda m: m.group(1) + str(count) + m.group(2), text)
        hits.append((pat, k))
    for pat, agree, forms in DECLINED.get(_current_file, []):
        form = agree(count, *forms)
        text, k = re.subn(pat, lambda m: m.group(1) + str(count) + " " + form + m.group(len(m.groups())), text)
        hits.append((pat, k))
    return text, hits


_current_file = None  # см. apply_patterns — простейший способ не тащить filename четвёртым параметром


def _run(write):
    count = wb_hit_count()
    changed = 0
    ok = True
    global _current_file
    for fname in set(PLAIN) | set(DECLINED):
        _current_file = fname
        path = os.path.join(ROOT, fname)
        text = open(path, encoding="utf8").read()
        new, hits = apply_patterns(text, count)
        for pat, k in hits:
            if k == 0:
                print("!! паттерн не нашёл совпадений в %s: %s" % (fname, pat))
                ok = False
        if new != text:
            if write:
                with open(path, "w", encoding="utf8") as f:
                    f.write(new)
                changed += 1
                print("обновлено: %s" % fname)
            else:
                print("!! %s: расходится с данными (нужен sync)" % fname)
                ok = False
    return count, changed, ok


def check():
    count, _, ok = _run(write=False)
    print(("sync-warehouse-counts: всё совпадает (%d)" if ok else "sync-warehouse-counts: РАСХОЖДЕНИЕ (данные=%d)") % count)
    return 0 if ok else 1


def main():
    count, changed, _ = _run(write=True)
    print("sync-warehouse-counts: WB hit=%d, файлов изменено=%d" % (count, changed))
    return 0


def demo():
    """Самопроверка БЕЗ побочных эффектов: страницы должны УЖЕ быть синхронизированы —
    если число (со склонением) на диске разошлось с data/warehouses.json, падает assert.
    Разошлось → сперва `python3 agents/sync-warehouse-counts.py` (без --demo/--check)."""
    count = wb_hit_count()
    assert count > 0
    for fname in set(PLAIN) | set(DECLINED):
        text = open(os.path.join(ROOT, fname), encoding="utf8").read()
        for pat in PLAIN.get(fname, []):
            assert re.search(pat.replace(r'\d+', str(count)), text), (
                "%s разошёлся с данными (нужен sync), якорь: %s" % (fname, pat))
        for pat, agree, forms in DECLINED.get(fname, []):
            form = agree(count, *forms)
            assert ("%d %s" % (count, form)) in text, (
                "%s разошёлся с данными (нужен sync), ожидали %r" % (fname, form))
    # согласование на синтетических числах — 1, 2, 5, 21, 22, 25, 11 (ловушка -надцать)
    assert ru_count(1, "о", "ф", "м") == "о"
    assert ru_count(2, "о", "ф", "м") == "ф"
    assert ru_count(4, "о", "ф", "м") == "ф"
    assert ru_count(5, "о", "ф", "м") == "м"
    assert ru_count(11, "о", "ф", "м") == "м"   # 11-14 — исключение, не "one"
    assert ru_count(21, "о", "ф", "м") == "о"
    assert ru_count(22, "о", "ф", "м") == "ф"
    assert ru_count(25, "о", "ф", "м") == "м"
    assert ru_count_gen(1, "о", "м") == "о"
    assert ru_count_gen(11, "о", "м") == "м"    # 11 — тоже исключение для родительного якоря
    assert ru_count_gen(21, "о", "м") == "о"
    assert ru_count_gen(5, "о", "м") == "м"
    print("demo OK (WB hit=%d)" % count)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--check" in sys.argv:
        sys.exit(check())
    else:
        sys.exit(main())
