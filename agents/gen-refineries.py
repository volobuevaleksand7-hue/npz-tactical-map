#!/usr/bin/env python3
"""gen-refineries — рендерит data-блоки /refineries из data/fuel-state.json.

Зачем: таблица заводов, разрез по регионам/операторам и список работающих — это
ПРОЕКЦИЯ fuel-state.json, который сборщик обновляет 4×/сутки. Пока блоки писались
руками, страница молча расходилась с данными: на 15.07 накопилось 12 расхождений
по 6 заводам (Саратовский на странице «~60%», в данных — остановлен вторым ударом
8 июля; ТАНЕКО наоборот). Счётчики 10/9/13 совпадали случайно — заводы поменялись
местами. Генератор убирает этот класс дрейфа целиком.

Что генерится (между маркерами <!-- GEN:x --> ... <!-- /GEN:x --> в refineries.html):
  table      — тело таблицы «Все НПЗ России» (32 строки)
  regions    — грид «НПЗ по регионам и городам»
  operators  — грид «НПЗ по операторам»
  working    — блок «Какие НПЗ работают сейчас»
  summary    — абзац прямого ответа со счётчиками и датой
  top5       — топ-5 по мощности

Проза, FAQ и JSON-LD остаются рукописными — но --check ловит их дрейф громко,
а не молча (это и есть главная защита; молчаливое враньё в проде хуже падения).

Использование:
    python3 agents/gen-refineries.py            # перегенерить блоки
    python3 agents/gen-refineries.py --check    # только проверить дрейф, ничего не писать
    python3 agents/gen-refineries.py --selftest # проверить логику без файлов

ponytail: только stdlib. Маркеры вместо шаблонизатора — проза страницы остаётся
рукописной, генератор трогает ровно свои блоки.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "fuel-state.json")
PAGE = os.path.join(ROOT, "refineries.html")

# id завода → слаг карточки /npz/. Только те, у кого карточка реально есть.
# Нет в словаре → в таблице обычным текстом (карточки пока нет).
CARDS = {
    "kinef": "kinef",
    "ryazan": "ryazanskij-npz",
    "moscow": "moskovskij-npz",
    "kuibyshev": "kujbyshevskij-npz",
    "nnos": "lukojl-norsi",
    "yanos": "slavneft-yanos",
    "omsk": "omskij-npz",
    "taneco": "taneko-npz",
    "ufa": "bashneft-ufa",
    "saratov": "saratovskij-npz",
    "ilsky": "ilskij-npz",
    "tuapse": "tuapsinskij-npz",
    "syzran": "syzranskij-npz",
    "afipsky": "afipskij-npz",
}

TAG = {"down": ("tag-down", "СТОП"), "partial": ("tag-partial", "ОГРАНИЧЕНО"),
       "operational": ("tag-operational", "РАБОТАЕТ")}
DOT = {"down": "red", "partial": "amber", "operational": "green"}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Короткое имя для гридов: «Славнефть-ЯНОС (Ярославский НПЗ)» → «Славнефть-ЯНОС».
# В таблице остаётся полное — там есть место.
SHORT = re.compile(r"\s*\([^)]*\)$")


def rus_date(iso):
    """2026-07-14 → «14 июля 2026». Правило проекта: видимые даты по-русски, не ISO."""
    y, m, d = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
    return f"{d} {MONTHS[m - 1]} {y}"


def short(name):
    return SHORT.sub("", name).strip()


def tokens(name):
    """Значимые слова названия. «НОРСИ (Кстово)» → {норси, кстово}."""
    return {w for w in re.findall(r"[\w\-]+", name.lower().replace("-", " ")) if len(w) >= 4}


def same_plant(a, b):
    """Один ли это завод. В тексте живут алиасы («НОРСИ (Кстово)» = данные
    «Лукойл-Нижегороднефтеоргсинтез (Кстово)») и усечения («Лукойл-Перм» =
    «Лукойл-Пермнефтеоргсинтез»), поэтому сверяем по общему префиксу токенов,
    а не по префиксу строки — иначе алиас даёт ложную тревогу."""
    for x in tokens(a):
        for y in tokens(b):
            if x[:4] == y[:4]:
                return True
    return False


def load():
    d = json.load(open(DATA, encoding="utf-8"))
    return d["refineries"], d["meta"]


def counts(R):
    c = Counter(r["status"] for r in R)
    return c["down"], c["partial"], c["operational"], len(R)


def render_table(R):
    out = []
    for r in sorted(R, key=lambda r: -r["capacity_mt_year"]):
        cls, label = TAG[r["status"]]
        slug = CARDS.get(r["id"])
        nm = f'<a href="/npz/{slug}">{r["name"]}</a>' if slug else r["name"]
        pct = r.get("est_output_pct")
        load_s = "—" if pct is None else ("0%" if pct == 0 else f"~{pct}%" if r["status"] != "operational" else "100%")
        ss = r.get("status_since")
        since = f"{ss[8:10]}.{ss[5:7]}" if ss else "—"
        out.append(f'          <tr><td>{nm}</td><td>{r["operator"]}</td><td>{r["region"]}</td>'
                   f'<td>{r["capacity_mt_year"]} млн т/г</td>'
                   f'<td><span class="{cls}">{label}</span></td><td>{load_s}</td><td>{since}</td></tr>')
    return "\n".join(out)


def _grid(groups, order):
    """Общий рендер грида: [(заголовок, [заводы])] → карточки. Регионы и операторы
    отличаются только заголовком, поэтому один рендер на оба."""
    out = ['      <div class="reg-grid">']
    for key in order:
        rs = groups[key]
        cap = sum(r["capacity_mt_year"] for r in rs)
        plants = " · ".join(
            f'<span style="white-space:nowrap"><span class="dot {DOT[r["status"]]}"></span>{short(r["name"])}</span>'
            for r in sorted(rs, key=lambda r: -r["capacity_mt_year"]))
        out.append(f'        <div class="reg-item"><div class="reg-name">{key} '
                   f'<span class="reg-cnt">· {len(rs)} · {cap:.1f} млн т/г</span></div>'
                   f'<div class="reg-plants">{plants}</div></div>')
    out.append("      </div>")
    return "\n".join(out)


def render_regions(R):
    g = defaultdict(list)
    for r in R:
        g[r["region"]].append(r)
    order = sorted(g, key=lambda k: (-len(g[k]), -sum(x["capacity_mt_year"] for x in g[k])))
    return _grid(g, order)


def render_operators(R):
    g = defaultdict(list)
    for r in R:
        g[r["operator"]].append(r)
    order = sorted(g, key=lambda k: (-len(g[k]), -sum(x["capacity_mt_year"] for x in g[k])))
    return _grid(g, order)


def render_working(R, meta):
    """«Какие НПЗ работают сейчас» — отдельный интент от «сколько НПЗ»."""
    w = sorted([r for r in R if r["status"] == "operational"], key=lambda r: -r["capacity_mt_year"])
    cap = sum(r["capacity_mt_year"] for r in w)
    tot = sum(r["capacity_mt_year"] for r in R)
    date = rus_date(meta["generated_at"][:10])
    items = "\n".join(
        f'        <li><strong>{short(r["name"])}</strong> — {r["capacity_mt_year"]} млн т/год, '
        f'{r["region"]}, {r["operator"]}</li>' for r in w)
    return (f'      <p class="lead-p">По состоянию на {date} в штатном режиме работают '
            f'<strong>{len(w)} из {len(R)}</strong> нефтеперерабатывающих заводов суммарной мощностью '
            f'<strong>{cap:.1f} млн т/год</strong> — это около {cap / tot * 100:.0f}% всех '
            f'нефтеперерабатывающих мощностей страны. Это действующие НПЗ, по которым на сегодня '
            f'нет данных об остановке или снижении загрузки:</p>\n'
            f'      <ol class="work-list">\n{items}\n      </ol>\n'
            f'      <p class="lead-p">Остальные заводы либо остановлены, либо работают с ограничениями — '
            f'их статусы и даты указаны в таблице выше. Статусы — оценка по открытым источникам, '
            f'они меняются по мере поступления данных.</p>')


def render_summary(R, meta):
    down, part, oper, tot = counts(R)
    cap = sum(r["capacity_mt_year"] for r in R)
    date = rus_date(meta["generated_at"][:10])
    return (f'        <p><strong>Сколько НПЗ в России на сегодня:</strong> по состоянию на {date}, '
            f'в каталоге ниже — <strong>{tot} крупных нефтеперерабатывающих завода</strong> суммарной '
            f'мощностью ~{cap:.0f} млн т/год. Из них на сегодня '
            f'<strong style="color:var(--red)">{down} полностью остановлены</strong> (выведены из строя), '
            f'<strong style="color:var(--amber)">{part} работают с ограничениями</strong> по загрузке и '
            f'<strong style="color:var(--green)">{oper} работают в штатном режиме</strong> — статусы и даты '
            f'по каждому заводу указаны в таблице и обновляются по мере поступления данных '
            f'OSINT-мониторинга.</p>')


def render_top5(R):
    top = sorted(R, key=lambda r: (-r["capacity_mt_year"], r["name"]))[:5]
    lines = []
    for i, r in enumerate(top, 1):
        slug = CARDS.get(r["id"])
        nm = f'<a href="/npz/{slug}">{short(r["name"])}</a>' if slug else short(r["name"])
        pct = r.get("est_output_pct")
        ss = r.get("status_since")
        when = f" с {rus_date(ss)}" if ss else ""
        if r["status"] == "down":
            state = f"Остановлен{when}."
        elif r["status"] == "partial":
            state = f"Работает ~{pct}%{when}." if pct is not None else f"Работает с ограничениями{when}."
        else:
            state = "Работает в штатном режиме."
        # регион в данных часто уже с точкой («Омская обл.») — иначе выходит «обл.. Остановлен»
        reg = r["region"].rstrip(".")
        lines.append(f'          <strong>{i}. {nm}</strong> — {r["capacity_mt_year"]} млн т/год, '
                     f'{reg}. {state}')
    body = "<br>\n".join(lines)
    ndown = sum(1 for r in top if r["status"] == "down")
    cap = sum(r["capacity_mt_year"] for r in top)
    tot = sum(r["capacity_mt_year"] for r in R)
    word = {1: "Один из пяти", 2: "Два из пяти", 3: "Три из пяти",
            4: "Четыре из пяти", 5: "Все пять"}.get(ndown, f"{ndown} из пяти")
    tail = (f'        <p style="margin-top:10px">{word} крупнейших НПЗ полностью остановлен'
            f'{"ы" if ndown != 1 else ""}. Суммарно они обеспечивали ~{cap / tot * 100:.0f}% всей '
            f'нефтепереработки РФ.</p>' if ndown else
            f'        <p style="margin-top:10px">Суммарно они обеспечивали ~{cap / tot * 100:.0f}% всей '
            f'нефтепереработки РФ.</p>')
    return f'        <p style="margin-top:10px">\n{body}\n        </p>\n{tail}'


BLOCKS = {
    "table": render_table,
    "regions": render_regions,
    "operators": render_operators,
    "working": lambda R, m: render_working(R, m),
    "summary": lambda R, m: render_summary(R, m),
    "top5": render_top5,
}


def splice(html, name, body):
    """Заменить содержимое между <!-- GEN:name --> и <!-- /GEN:name -->."""
    pat = re.compile(rf"(<!-- GEN:{name} -->\n).*?(\n\s*<!-- /GEN:{name} -->)", re.S)
    if not pat.search(html):
        sys.exit(f"нет маркеров GEN:{name} в refineries.html")
    return pat.sub(lambda m: m.group(1) + body + m.group(2), html)


def check(R, meta, html):
    """Ловит дрейф прозы/JSON-LD, которые генератор не владеет. Молчаливое
    расхождение в проде опаснее падения — поэтому шумим."""
    problems = []
    down, part, oper, tot = counts(R)
    date = rus_date(meta["generated_at"][:10])

    # 1. Дата «состояния/сегодня» в прозе/FAQ/JSON-LD. Формы: «по состоянию на X»,
    # «На X полностью остановлены», «На сегодня (X) из них». Регистр важен: FAQ и
    # JSON-LD начинают предложение с заглавной «По»/«На» — strict-паттерн их
    # пропускал, и дрейф FAQ («14 июля» при данных «16 июля») молча дожил до прода
    # (16.07). Исторические даты («остановлен 6 июля», «после удара 5 мая») сюда НЕ
    # попадают — они без маркеров «состояния».
    if f"{tot} " not in html:
        problems.append(f"число заводов {tot} не встречается в тексте")
    state_dates = set(re.findall(r"[Пп]о состоянию на (\d{1,2} \w+ \d{4})", html))
    state_dates |= set(re.findall(r"[Нн]а (?:сегодня \()?(\d{1,2} \w+ \d{4})\)? (?:из них|полностью остановлен)", html))
    stale_dates = state_dates - {date}
    if stale_dates:
        problems.append(f"устаревшая дата в тексте: {sorted(stale_dates)} (данные на {date})")

    # 2. Статусы заводов в JSON-LD/FAQ: имена остановленных должны совпадать с данными
    names_down = {r["name"] for r in R if r["status"] == "down"}
    for m in re.finditer(r"полностью остановлены \d+ НПЗ: ([^.<\"]+)", html):
        listed = {x.strip() for x in m.group(1).split(",")}
        for nm in listed:
            if not any(same_plant(nm, d) for d in names_down):
                problems.append(f"в списке остановленных значится «{nm}», но в данных он не down")
        for d_ in names_down:
            if not any(same_plant(x, d_) for x in listed):
                problems.append(f"завод «{d_}» остановлен в данных, но его нет в списке остановленных")

    # 3. JSON-LD валиден + FAQ-разметка совпадает с видимым текстом (прецедент: разъезжались)
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    schema_q = []
    for b in blocks:
        try:
            o = json.loads(b)
        except Exception as e:
            problems.append(f"невалидный JSON-LD: {e}")
            continue
        if o.get("@type") == "FAQPage":
            schema_q = [q["name"] for q in o.get("mainEntity", [])]
    vis_q = re.findall(r"toggle\('open'\)\">([^<]+)</div>", html)
    for q in schema_q:
        if q not in vis_q:
            problems.append(f"вопрос есть в JSON-LD, но не в видимом FAQ: «{q}»")
    for q in vis_q:
        if q not in schema_q:
            problems.append(f"вопрос есть в видимом FAQ, но не в JSON-LD: «{q}»")
    return problems


def selftest():
    R = [
        {"id": "omsk", "name": "Омский НПЗ", "operator": "Газпром нефть", "region": "Омская обл.",
         "capacity_mt_year": 22.0, "status": "down", "status_since": "2026-07-06", "est_output_pct": 0},
        {"id": "x1", "name": "Тестовый НПЗ (Сити)", "operator": "Газпром нефть", "region": "Омская обл.",
         "capacity_mt_year": 10.0, "status": "operational", "status_since": None, "est_output_pct": 100},
        {"id": "x2", "name": "Второй НПЗ", "operator": "Лукойл", "region": "Пермский край",
         "capacity_mt_year": 5.0, "status": "partial", "status_since": "2026-07-08", "est_output_pct": 40},
    ]
    meta = {"generated_at": "2026-07-14T10:30:00Z"}
    assert counts(R) == (1, 1, 1, 3), counts(R)
    assert rus_date("2026-07-14") == "14 июля 2026"
    assert short("Тестовый НПЗ (Сити)") == "Тестовый НПЗ"

    t = render_table(R)
    assert '<a href="/npz/omskij-npz">Омский НПЗ</a>' in t, "карточка должна линковаться"
    assert "Тестовый НПЗ (Сити)</td>" in t, "без карточки — обычный текст"
    assert t.index("Омский") < t.index("Тестовый"), "сортировка по мощности убыв."
    assert "<td>06.07</td>" in t and "<td>—</td>" in t, "даты статуса"

    o = render_operators(R)
    assert "Газпром нефть <span class=\"reg-cnt\">· 2 · 32.0" in o, o[:200]
    assert 'dot red' in o and 'dot green' in o and 'dot amber' in o

    w = render_working(R, meta)
    assert "<strong>1 из 3</strong>" in w and "14 июля 2026" in w

    s = render_summary(R, meta)
    assert "1 полностью остановлены" in s and "3 крупных" in s

    t5 = render_top5(R)
    assert "Один из пяти" in t5 and "Остановлен с 6 июля 2026" in t5
    assert "Работает ~40%" in t5
    assert ".." not in t5, "регион с точкой не должен давать «обл.. Остановлен»"

    # алиасы: детектор не должен верещать на «НОРСИ (Кстово)» vs данные «Лукойл-Ниж... (Кстово)»
    assert same_plant("НОРСИ (Кстово)", "Лукойл-Нижегороднефтеоргсинтез (Кстово)")
    assert same_plant("Лукойл-Перм", "Лукойл-Пермнефтеоргсинтез")
    assert same_plant("Московский (Капотня)", "Московский НПЗ (Капотня)")
    assert not same_plant("Омский", "Рязанский НПЗ")

    # splice
    html = "a\n<!-- GEN:table -->\nOLD\n      <!-- /GEN:table -->\nb"
    assert "NEW" in splice(html, "table", "NEW") and "OLD" not in splice(html, "table", "NEW")

    # check ловит дрейф даты и подменённый статус
    bad = "<p>по состоянию на 12 июля 2026</p> 3 завода"
    assert any("устаревшая дата" in p for p in check(R, meta, bad)), check(R, meta, bad)
    # регистр: заглавные «По состоянию на» / «На X ... остановлены» раньше пропускались
    up1 = "3 завода. По состоянию на 12 июля 2026 полностью остановлены."
    assert any("устаревшая дата" in p for p in check(R, meta, up1)), check(R, meta, up1)
    up2 = "3 завода. На 12 июля 2026 полностью остановлены 1 НПЗ."
    assert any("устаревшая дата" in p for p in check(R, meta, up2)), check(R, meta, up2)
    # актуальная дата (14 июля из meta) НЕ должна триггерить, историческая — тоже нет
    ok_html = "3 завода. По состоянию на 14 июля 2026. Омский остановлен 6 июля 2026 после удара."
    assert not any("устаревшая дата" in p for p in check(R, meta, ok_html)), check(R, meta, ok_html)
    drift = ('3 завода по состоянию на 14 июля 2026 '
             'полностью остановлены 1 НПЗ: Второй НПЗ.')
    ps = check(R, meta, drift)
    assert any("Второй НПЗ" in p for p in ps), ps      # он partial, а не down
    assert any("Омский" in p for p in ps), ps          # он down, но не перечислен
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="рендер data-блоков /refineries из fuel-state.json")
    ap.add_argument("--check", action="store_true", help="только проверить дрейф, не писать")
    ap.add_argument("--selftest", action="store_true", help="проверить логику без файлов")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    R, meta = load()
    html = open(PAGE, encoding="utf-8").read()
    down, part, oper, tot = counts(R)
    print(f"данные на {meta['generated_at']}: {tot} НПЗ = {down} стоп + {part} огранич + {oper} работают")

    if not a.check:
        for name, fn in BLOCKS.items():
            body = fn(R, meta) if fn.__code__.co_argcount == 2 else fn(R)
            html = splice(html, name, body)
        open(PAGE, "w", encoding="utf-8").write(html)
        print("блоки перегенерены:", ", ".join(BLOCKS))

    problems = check(R, meta, html)
    if problems:
        print("\n🔴 ДРЕЙФ (проза/JSON-LD расходятся с данными):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("check OK — проза и JSON-LD согласованы с данными")


if __name__ == "__main__":
    main()
