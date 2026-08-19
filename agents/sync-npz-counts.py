#!/usr/bin/env python3
"""Число заводов/остановлено/ограничено/штатно/повреждено на РУКОПИСНЫХ страницах —
из data/fuel-state.json (по образцу agents/sync-warehouse-counts.py, прочитай его
первым, если непонятна конструкция).

/refineries и /krupnejshie-npz-rossii генерируются agents/gen-refineries.py и уже
живые — их сюда НЕ включать. Здесь — только ручной HTML, где то же самое число
вбито в текст руками и расходится с data/ без присмотра: на 18.08.2026 найдено
"32 завода" (устарело до 33), "10 работают с ограничениями" (устарело до 12),
"21/22 завода одновременно повреждены" (расходятся друг с другом и с 23).

Каждое вхождение поймано СВОИМ regex-якорем (окружающий литеральный текст, не
цифра сама по себе) — на страницах полно дат вида "22 июля", "11 августа", и
слепая замена по значению рано или поздно испортит дату, совпавшую со счётчиком.

🔴 Датированные утверждения ("По состоянию на середину июля...", "На 22 июля...")
сюда НЕ идут, даже если несут те же числа — они чинятся руками при следующем
content-обновлении (вместе с датой), не автосинком. Пример: attacks.html хранит
такую фразу про "середину июля" и деficit.html — список "Полностью остановлены N
НПЗ: <имена>" (состав завода meняется, это не голое число) — оба правятся вручную,
не здесь.

Русское склонение — тот же ru_count/ru_count_gen, что в sync-warehouse-counts.py:
ru_count — числительное КАК ПОДЛЕЖАЩЕЕ ("23 завода", "21 завод", "25 заводов").
ru_count_gen — числительное в родительном под предлогом/квантором ("из 33
заводов", "всех 33 заводов" — падеж всегда родительный, one/many зависит только
от того, оканчивается ли число на "один" (1, 21, 31…, но не 11)).

Запуск (пишет файлы):     python3 agents/sync-npz-counts.py
Проверка без записи:      python3 agents/sync-npz-counts.py --check
Самопроверка (assert):    python3 agents/sync-npz-counts.py --demo
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS_SRC = os.path.join(ROOT, "data", "fuel-state.json")


def ru_count(n, one, few, many):
    """21 завод, 22/23/24 завода, 10/11..20/25 заводов — числительное-подлежащее."""
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
    """Родительный под предлогом/квантором ("из/всех N заводов") — только форма
    на "1" (кроме 11) отличается ("завода"), остальные — "заводов"."""
    n100 = n % 100
    n10 = n % 10
    if n10 == 1 and n100 != 11:
        return one
    return many


def _refineries():
    with open(FS_SRC, encoding="utf8") as f:
        return json.load(f)["refineries"]


def total_count():
    return len(_refineries())


def down_count():
    return sum(1 for r in _refineries() if r["status"] == "down")


def partial_count():
    return sum(1 for r in _refineries() if r["status"] == "partial")


def normal_count():
    return sum(1 for r in _refineries() if r["status"] == "operational")


def damaged_count():
    return down_count() + partial_count()


def down_capacity_mt():
    return round(sum(r["capacity_mt_year"] for r in _refineries() if r["status"] == "down"), 1)


def down_capacity_pct():
    refs = _refineries()
    total_cap = sum(r["capacity_mt_year"] for r in refs)
    return round(down_capacity_mt() / total_cap * 100)


def throughput_shortfall_pct():
    """Недобор с учётом частично работающих — взвешенная по мощности недопоставка
    (совпадает с national_balance.throughput_shortfall_pct в fuel-state.json,
    пересчитывается заново из refineries[], чтобы не тащить отдельный источник)."""
    refs = _refineries()
    total_cap = sum(r["capacity_mt_year"] for r in refs)
    avail = sum(r["capacity_mt_year"] * r.get("est_output_pct", 0) / 100 for r in refs)
    return round(100 - avail / total_cap * 100)


def total_capacity_mt():
    return round(sum(r["capacity_mt_year"] for r in _refineries()), 1)


def mt_str(x):
    """Российский формат мощности с запятой: 338.4 -> "338,4"."""
    return ("%.1f" % x).replace(".", ",")


def _ref(rid):
    return next(r for r in _refineries() if r["id"] == rid)


def refinery_share_pct(rid):
    """Доля мощности ОДНОГО завода в общероссийской, округлённая."""
    total_cap = sum(r["capacity_mt_year"] for r in _refineries())
    return round(_ref(rid)["capacity_mt_year"] / total_cap * 100)


def refinery_output_pct(rid):
    return round(_ref(rid)["est_output_pct"])


KRASNODAR_KRAI = ("tuapse", "afipsky", "ilsky", "slavyansk", "krasnodar-rn")


def krai_available_pct():
    """Взвешенная реальная доступность мощностей 5 НПЗ Краснодарского края
    (widget на krasnodar.html: "реально доступно около N% мощностей края")."""
    refs = [r for r in _refineries() if r["id"] in KRASNODAR_KRAI]
    total_cap = sum(r["capacity_mt_year"] for r in refs)
    avail = sum(r["capacity_mt_year"] * r.get("est_output_pct", 0) / 100 for r in refs)
    return round(avail / total_cap * 100)


METRICS = {
    "total": total_count,
    "down": down_count,
    "partial": partial_count,
    "normal": normal_count,
    "damaged": damaged_count,
    "down_cap_mt": down_capacity_mt,
    "down_cap_pct": down_capacity_pct,
    "shortfall_pct": throughput_shortfall_pct,
    "total_cap_mt": total_capacity_mt,
    "kinef_share_pct": lambda: refinery_share_pct("kinef"),
    "tuapse_pct": lambda: refinery_output_pct("tuapse"),
    "afipsky_pct": lambda: refinery_output_pct("afipsky"),
    "ilsky_pct": lambda: refinery_output_pct("ilsky"),
    "slavyansk_pct": lambda: refinery_output_pct("slavyansk"),
    "krasnodar_rn_pct": lambda: refinery_output_pct("krasnodar-rn"),
    "krai_available_pct": krai_available_pct,
}

NPZ = ("завод", "завода", "заводов")

# --- якоря без склонения: "НПЗ" — аббревиатура, число рода/падежа не меняет ---
# (файл, [(метрика, regex с ОДНОЙ группой \d+ в стабильном литеральном контексте)])
PLAIN = {
    "situaciya-s-benzinom.html": [
        ("total", r'(Статусы всех )\d+( НПЗ на карте)'),
        ("down_cap_pct", r'(<div class="status-card"><div class="val">)\d+(%</div><div class="lbl">мощностей выбито полностью</div></div>)'),
        ("shortfall_pct", r'(<div class="status-card"><div class="val">)\d+(%</div><div class="lbl">недобор с учётом частичных</div></div>)'),
    ],
    "npz-lukojla.html": [
        ("total", r'(Все )\d+( НПЗ России: мощности и статусы →)'),
    ],
    "npz-gazprom-nefti.html": [
        ("total", r'(Все )\d+( НПЗ России: мощности и статусы →)'),
    ],
    "npz-rosnefti.html": [
        ("total", r'(Все )\d+( НПЗ России: мощности и статусы →)'),
    ],
    "talony.html": [
        ("total", r'(Из )\d+( крупных НПЗ страны часть полностью остановлена)'),
        ("down_cap_pct", r'(из строя выведено около )\d+(% перерабатывающих мощностей)'),
        ("down_cap_pct", r'(<div class="val">)\d+(%</div>\s*<div class="lbl">потеря мощностей НПЗ РФ</div>)'),
        ("down_cap_pct", r'(совокупно выбыло около <strong>)\d+(% перерабатывающих мощностей</strong>)'),
        ("down_cap_pct", r'(выбыло около )\d+(% мощностей\.)'),
    ],
    "moskva.html": [
        ("down_cap_pct", r'(и общим выбытием около )\d+(% перерабатывающих мощностей РФ)'),
        ("down_cap_pct", r'(и общее выбытие около )\d+(% перерабатывающих мощностей РФ)'),
        ("down_cap_pct", r'(выбытием ~)\d+(% мощностей РФ)'),
    ],
    "npz/kinef.html": [
        ("kinef_share_pct", r'(второй по мощности в стране — около )\d+(% всей нефтепереработки РФ)'),
        ("kinef_share_pct", r'(на него приходится около )\d+(% всей российской нефтепереработки)'),
        ("kinef_share_pct", r'(на завод приходится около )\d+(% переработки страны)'),
        ("kinef_share_pct", r'(около )\d+(% всей переработки страны и первое место по мощности)'),
    ],
    "npz/slavneft-yanos.html": [
        ("down_cap_pct", r'(на фоне общего кризиса переработки: около )\d+(% мощностей НПЗ страны остановлено полностью)'),
        ("shortfall_pct", r'(совокупный недобор с учётом частично работающих заводов — около )\d+(%\)\.)'),
    ],
    "krasnodar.html": [
        ("tuapse_pct", r'(<span class="station-name">Туапсинский НПЗ</span><span class="station-status limited">)\d+(%</span>)'),
        ("afipsky_pct", r'(<span class="station-name">Афипский НПЗ</span><span class="station-status limited">)\d+(%</span>)'),
        ("ilsky_pct", r'(<span class="station-name">Ильский НПЗ</span><span class="station-status limited">)\d+(%</span>)'),
        ("slavyansk_pct", r'(<span class="station-name">Славянский НПЗ</span><span class="station-status limited">)\d+(%</span>)'),
        ("krasnodar_rn_pct", r'(<span class="station-name">Краснодарский НПЗ</span><span class="station-status ok">)\d+(%</span>)'),
        ("krai_available_pct", r'(реально доступно около )\d+(% мощностей края)'),
        ("tuapse_pct", r'(Туапсинский НПЗ \(крупнейший в крае, 12 млн т/год\) с 31 июля частично перезапущен \(около )\d+(% загрузки\))'),
        ("tuapse_pct", r'(Туапсинский НПЗ \(Роснефть, 12 млн т/год — частично, )\d+(%\))'),
        ("tuapse_pct", r'(Туапсинский \(Роснефть, 12 млн т/год — )\d+(%\), Афипский)'),
    ],
}

# --- якоря со склонением: (метрика, regex(есть \d+ (?:завод|завода|заводов) с
#     группами prefix/suffix), функция согласования, формы) ---
DECLINED = {
    "situaciya-s-benzinom.html": [
        ("total", r'(Все )\d+ (?:завод|завода|заводов)( и их состояние)', ru_count, NPZ),
    ],
    "npz-lukojla.html": [
        ("total", r'(<div class="lc-d">)\d+ (?:завод|завода|заводов)(: мощности, статусы, разрез по операторам</div>)', ru_count, NPZ),
    ],
    "npz-gazprom-nefti.html": [
        ("total", r'(<div class="lc-d">)\d+ (?:завод|завода|заводов)(: мощности, статусы, разрез по операторам</div>)', ru_count, NPZ),
    ],
    "npz-rosnefti.html": [
        ("total", r'(<div class="lc-d">)\d+ (?:завод|завода|заводов)(: мощности, статусы, разрез по операторам</div>)', ru_count, NPZ),
    ],
    "npz/astrahanskij-gpz.html": [
        ("total", r'(Список всех )\d+ (?:завод|завода|заводов)( России со статусами)', ru_count_gen, ("завода", "заводов")),
    ],
    "npz/angarskij-npz.html": [
        ("total", r'(Список всех )\d+ (?:завод|завода|заводов)( России со статусами)', ru_count_gen, ("завода", "заводов")),
    ],
    "skorost-remonta-npz.html": [
        ("damaged", r'(Плюс одновременно повреждён )\d+ (?:завод|завода|заводов)(, и ремонтные бригады)', ru_count, NPZ),
        ("damaged", r'(Одновременно повреждён )\d+ (?:завод|завода|заводов)(\. Специализированные)', ru_count, NPZ),
    ],
}

# --- якоря с несколькими числами в одной фразе: (regex с N+1 литеральными
#     группами вокруг N чисел, функция сборки замены из groups()) ---
MULTI = {
    "crisis.html": [
        (r'(в июне, Bloomberg\)\. )\d+( крупных НПЗ полностью остановлены, ещё )\d+( работают с ограничениями\.)',
         lambda g: g[0] + str(down_count()) + g[1] + str(partial_count()) + g[2]),
    ],
    "deficit.html": [
        (r'(Из )\d+( крупных НПЗ страны )\d+( полностью остановлены, ещё )\d+( работают с ограничениями\.)',
         lambda g: g[0] + str(total_count()) + g[1] + str(down_count()) + g[2] + str(partial_count()) + g[3]),
        (r'(Из )\d+( крупных НПЗ )\d+( полностью остановлены, ещё )\d+( работают с ограничениями\.)',
         lambda g: g[0] + str(total_count()) + g[1] + str(down_count()) + g[2] + str(partial_count()) + g[3]),
        (r'(Из )\d+( крупных НПЗ — )\d+( полностью остановлены, )\d+( работают с ограничениями\.)',
         lambda g: g[0] + str(total_count()) + g[1] + str(down_count()) + g[2] + str(partial_count()) + g[3]),
        (r'(Совокупная потеря мощностей — около )\d+(% \()\d+,\d+( из )\d+,\d+( млн тонн/год\)\.)',
         lambda g: g[0] + str(down_capacity_pct()) + g[1] + mt_str(down_capacity_mt()) + g[2] + mt_str(total_capacity_mt()) + g[3]),
        (r'(<div class="st">Падение переработки на )\d+(%</div><div class="se">)\d+,\d+( из )\d+,\d+( млн тонн/год мощностей простаивают\. Bloomberg: минимум переработки с 2005 года\.</div>)',
         lambda g: g[0] + str(down_capacity_pct()) + g[1] + mt_str(down_capacity_mt()) + g[2] + mt_str(total_capacity_mt()) + g[3]),
    ],
    "attacks.html": [
        # "20" (сколько заводов затрагивалось ударами хоть раз, кумулятивно с апреля) —
        # отдельная метрика, которой нет в fuel-state.json (только текущие статусы);
        # якорь трогает только знаменатель "из 32/33"
        (r'(Затронуто \d+ из )\d+( крупных НПЗ\.)',
         lambda g: g[0] + str(total_count()) + g[1]),
    ],
    "situaciya-s-benzinom.html": [
        (r'(из )\d+ (?:завод|завода|заводов)( <strong>)\d+( стоят полностью, )\d+( работают на пониженной загрузке и )\d+( — в штатном режиме</strong>)',
         lambda g: (g[0] + str(total_count()) + " " + ru_count_gen(total_count(), "завода", "заводов") + g[1]
                    + str(down_count()) + g[2] + str(partial_count()) + g[3] + str(normal_count()) + g[4])),
    ],
    "krasnodar.html": [
        (r'(Туапсинский работает на )\d+(% \(с 31 июля вышел из полной остановки\), Афипский работает на )\d+(%, Ильский — на )\d+(%, Славянский — на )\d+(%\.)',
         lambda g: (g[0] + str(refinery_output_pct("tuapse")) + g[1] + str(refinery_output_pct("afipsky"))
                    + g[2] + str(refinery_output_pct("ilsky")) + g[3] + str(refinery_output_pct("slavyansk")) + g[4])),
    ],
}


def _apply_multi(text, pattern, build):
    m = re.search(pattern, text)
    if not m:
        return text, 0
    replacement = build(list(m.groups()))
    return re.subn(pattern, lambda mm: replacement, text)


def apply_patterns(text, fname):
    """Возвращает (новый_текст, [(pattern, число_замен), ...])."""
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
    for pat, build in MULTI.get(fname, []):
        text, k = _apply_multi(text, pat, build)
        hits.append((pat, k))
    return text, hits


def _files():
    return set(PLAIN) | set(DECLINED) | set(MULTI)


def _run(write):
    changed = 0
    ok = True
    for fname in _files():
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
    print("sync-npz-counts: %s (всего=%d, остановлено=%d, ограничено=%d, штатно=%d, повреждено=%d)"
          % ("всё совпадает" if ok else "РАСХОЖДЕНИЕ", total_count(), down_count(), partial_count(),
             normal_count(), damaged_count()))
    return 0 if ok else 1


def main():
    changed, _ = _run(write=True)
    print("sync-npz-counts: всего=%d, остановлено=%d, файлов изменено=%d" % (total_count(), down_count(), changed))
    return 0


def demo():
    """Самопроверка БЕЗ побочных эффектов: страницы должны УЖЕ быть синхронизированы.
    Разошлось → сперва `python3 agents/sync-npz-counts.py` (без --demo/--check)."""
    assert total_count() > 0
    for fname in _files():
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
        for pat, build in MULTI.get(fname, []):
            new_text, k = _apply_multi(text, pat, build)
            assert k > 0, "%s: якорь MULTI не найден, нужен sync: %s" % (fname, pat)
            assert new_text == text, "%s разошёлся с данными (нужен sync), якорь: %s" % (fname, pat)

    # согласование на синтетических числах — 1, 2, 5, 21, 22, 23, 11 (ловушка -надцать)
    assert ru_count(1, "о", "ф", "м") == "о"
    assert ru_count(2, "о", "ф", "м") == "ф"
    assert ru_count(4, "о", "ф", "м") == "ф"
    assert ru_count(5, "о", "ф", "м") == "м"
    assert ru_count(11, "о", "ф", "м") == "м"
    assert ru_count(21, "о", "ф", "м") == "о"
    assert ru_count(22, "о", "ф", "м") == "ф"
    assert ru_count(23, "о", "ф", "м") == "ф"
    assert ru_count(25, "о", "ф", "м") == "м"
    assert ru_count_gen(1, "о", "м") == "о"
    assert ru_count_gen(11, "о", "м") == "м"
    assert ru_count_gen(21, "о", "м") == "о"
    assert ru_count_gen(33, "о", "м") == "м"
    print("demo OK (всего=%d, остановлено=%d, ограничено=%d, штатно=%d, повреждено=%d, offline=%.1f млн т/год ~%d%%)"
          % (total_count(), down_count(), partial_count(), normal_count(), damaged_count(),
             down_capacity_mt(), down_capacity_pct()))


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--check" in sys.argv:
        sys.exit(check())
    else:
        sys.exit(main())
