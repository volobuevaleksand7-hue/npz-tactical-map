#!/usr/bin/env python3
"""Число поражённых/уцелевших складов Wildberries на РУКОПИСНЫХ страницах — из data/warehouses.json.

Ни одна из четырёх страниц ниже не генерируется скриптом (как /skolko-skladov-
wildberries-ozon через gen-warehouses-page.py) — это ручной HTML со счётчиком,
вбитым в текст. Счётчик расходится с данными за несколько дней без присмотра:
01.08 (17→19) и 18.08 (25→28 на udar-po-skladu-ozon/ceny-marketpleysy; 15→14 и
34→33 на ataki-na-sklady-wildberries-hronika/kakie-sklady-wildberries-ostalis —
эти две страницы вообще не были известны скрипту). Здесь синхронизируется ТОЛЬКО
число — остальной текст страниц остаётся ручным.

Каждое вхождение найдено по своему regex-якорю (окружающий литеральный текст, без
самой цифры) — не глобальная замена "19"→"21": на странице уже есть даты вроде
"31 июля", и слепая замена по значению рано или поздно испортит дату, совпавшую со
счётчиком.

🔴 Датированные исторические утверждения («на 7 августа было 25 объектов») сюда
НЕ идут — только якоря, которые всегда описывают ТЕКУЩЕЕ состояние (например,
цифра в отдельном div.val рядом с постоянной подписью, без даты в том же узле).
Датированные фразы правятся руками при следующем content-обновлении хроники.

🔴 Часть якорей ("N объектов" и т.п.) требуют русского склонения по числительному —
"19 объектов", но "21 объект", "22 объекта". Просто воткнуть цифру недостаточно:
на 21 склад слепая подстановка дала бы "21 объектов" (неверно). ru_count() — тот же
one/few/many, что в стандартных таблицах множественных форм CLDR/ICU для ru (без
более тонкого учёта падежа — этого различия сайты с цифрами в тексте обычно не
делают, и это осознанное упрощение).

Метрика у каждого якоря своя (см. METRICS): "поражено WB" — один счётчик,
"осталось WB/Ozon/всего" — другие, поэтому у якоря есть третий (PLAIN) или первый
(DECLINED) элемент — имя метрики, а не одно глобальное число на файл.

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


def _warehouses():
    with open(WH_SRC, encoding="utf8") as f:
        return json.load(f)["warehouses"]


def wb_hit_count():
    return sum(1 for w in _warehouses() if w["status"] == "hit" and w["operator"] == "wb")


def wb_ok_count():
    return sum(1 for w in _warehouses() if w["status"] == "ok" and w["operator"] == "wb")


def ozon_ok_count():
    return sum(1 for w in _warehouses() if w["status"] == "ok" and w["operator"] == "ozon")


def total_ok_count():
    return sum(1 for w in _warehouses() if w["status"] == "ok")


METRICS = {
    "wb_hit": wb_hit_count,
    "wb_ok": wb_ok_count,
    "ozon_ok": ozon_ok_count,
    "total_ok": total_ok_count,
}

# --- якоря без склонения: после числа сразу нелитеральный текст без сущ. (эллипсис/лейбл) ---
# (файл, [(метрика из METRICS, regex с ОДНОЙ группой \d+ в стабильном литеральном контексте)])
PLAIN = {
    "udar-po-skladu-ozon.html": [
        ("wb_hit", r'(объектов против )\d+( — три проверяемые причины)'),
        ("wb_hit", r'(объектов против )\d+(</strong> у Wildberries)'),
        ("wb_hit", r'(<div class="val">)\d+(</div><div class="lbl">поражённых складов Wildberries</div>)'),
        ("wb_hit", r'(таких объектов уже )\d+(\.)'),
    ],
    "ceny-marketpleysy-posle-udarov.html": [
        ("wb_hit", r'(<div class="val">)\d+(</div><div class="lbl">поражённых складов Wildberries</div>)'),
    ],
    "ataki-na-sklady-wildberries-hronika.html": [
        ("wb_hit", r'(<div class="status-card"><div class="val">)\d+( объектов</div><div class="lbl">уникальных складов сети Wildberries)'),
    ],
    "kakie-sklady-wildberries-ostalis.html": [
        ("total_ok", r'(<div class="status-card"><div class="val">)\d+(</div><div class="lbl">объектов без сообщений об ударе</div></div>)'),
        ("wb_ok", r'(<div class="status-card"><div class="val">)\d+(</div><div class="lbl">Wildberries</div></div>)'),
        ("ozon_ok", r'(<div class="status-card"><div class="val">)\d+(</div><div class="lbl">Ozon</div></div>)'),
    ],
}

# --- якоря со склонением: (метрика, regex с prefix/suffix группами + альтернативой из трёх
#     форм, функция согласования, формы one/few/many) ---
DECLINED = {
    "udar-po-skladu-ozon.html": [
        ("wb_hit", r'(поражено уже )\d+ (объект|объекта|объектов)(\.)',
         ru_count, ("объект", "объекта", "объектов")),
        ("wb_hit", r'(закономерность\.</strong> )\d+ (поражённый объект|поражённых объекта|поражённых объектов)( — выборка)',
         ru_count, ("поражённый объект", "поражённых объекта", "поражённых объектов")),
        ("wb_hit", r'(Помимо )\d+ (объекта|объектов)( Wildberries)',
         ru_count_gen, ("объекта", "объектов")),
        ("wb_hit", r'(выборки — )\d+ (поражённого объекта|поражённых объектов)( недостаточно)',
         ru_count_gen, ("поражённого объекта", "поражённых объектов")),
    ],
    "ceny-marketpleysy-posle-udarov.html": [
        ("wb_hit", r'(поражено <strong>)\d+ (складской объект|складских объекта|складских объектов)( Wildberries</strong>)',
         ru_count, ("складской объект", "складских объекта", "складских объектов")),
    ],
}


def apply_patterns(text, fname):
    """Возвращает (новый_текст, [(pattern, число_замен), ...]) — метрика своя у каждого якоря."""
    hits = []
    for metric, pat in PLAIN.get(fname, []):
        count = METRICS[metric]()
        text, k = re.subn(pat, lambda m: m.group(1) + str(count) + m.group(2), text)
        hits.append((pat, k))
    for metric, pat, agree, forms in DECLINED.get(fname, []):
        count = METRICS[metric]()
        form = agree(count, *forms)
        text, k = re.subn(pat, lambda m: m.group(1) + str(count) + " " + form + m.group(len(m.groups())), text)
        hits.append((pat, k))
    return text, hits


def _run(write):
    changed = 0
    ok = True
    for fname in set(PLAIN) | set(DECLINED):
        path = os.path.join(ROOT, fname)
        text = open(path, encoding="utf8").read()
        new, hits = apply_patterns(text, fname)
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
    return changed, ok


def check():
    _, ok = _run(write=False)
    print("sync-warehouse-counts: %s (WB поражено=%d, WB осталось=%d, Ozon осталось=%d, всего осталось=%d)"
          % ("всё совпадает" if ok else "РАСХОЖДЕНИЕ", wb_hit_count(), wb_ok_count(), ozon_ok_count(), total_ok_count()))
    return 0 if ok else 1


def main():
    changed, _ = _run(write=True)
    print("sync-warehouse-counts: WB hit=%d, файлов изменено=%d" % (wb_hit_count(), changed))
    return 0


def demo():
    """Самопроверка БЕЗ побочных эффектов: страницы должны УЖЕ быть синхронизированы —
    если число (со склонением) на диске разошлось с data/warehouses.json, падает assert.
    Разошлось → сперва `python3 agents/sync-warehouse-counts.py` (без --demo/--check)."""
    assert wb_hit_count() > 0
    for fname in set(PLAIN) | set(DECLINED):
        text = open(os.path.join(ROOT, fname), encoding="utf8").read()
        for metric, pat in PLAIN.get(fname, []):
            count = METRICS[metric]()
            assert re.search(pat.replace(r'\d+', str(count)), text), (
                "%s разошёлся с данными (нужен sync), якорь: %s" % (fname, pat))
        for metric, pat, agree, forms in DECLINED.get(fname, []):
            count = METRICS[metric]()
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
    print("demo OK (WB hit=%d, WB ok=%d, Ozon ok=%d, total ok=%d)"
          % (wb_hit_count(), wb_ok_count(), ozon_ok_count(), total_ok_count()))


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--check" in sys.argv:
        sys.exit(check())
    else:
        sys.exit(main())
