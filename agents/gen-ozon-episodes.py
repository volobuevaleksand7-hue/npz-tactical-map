#!/usr/bin/env python3
"""Изменчивые куски udar-po-skladu-ozon.html — из data/warehouses.json.

Страница ручная: авторские абзацы с деталями эпизодов (эвакуации, пострадавшие)
в датасете не лежат и генерации не подлежат. Генератор владеет только тем, что
реально дрейфует после каждого удара: списком городов в лиде, датированным
перечнем эпизодов, абзацем счётчиков и двумя ответами FAQ, где есть числа.

Почему так: 24.08 счётчики на этой странице синкались автоматикой, а проза —
нет, и страница за двое суток начала противоречить сама себе («три объекта»
в тексте против «7» в статкартах). Руками этот список не удержать.
"""
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "udar-po-skladu-ozon.html")
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря")


def load_data():
    spec = importlib.util.spec_from_file_location(
        "gwp", os.path.join(ROOT, "agents", "gen-warehouses-page.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_data()


def rus_date(iso):
    """«2026-08-22» -> «22 августа». Русский формат — правило проекта, не ISO."""
    y, m, d = iso[:10].split("-")
    return "%d %s" % (int(d), MONTHS[int(m) - 1])


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def split(doc):
    wh = doc["warehouses"]
    oz = [w for w in wh if w.get("operator") == "ozon"]
    wb = [w for w in wh if w.get("operator") == "wb"]
    oz_hit = sorted((w for w in oz if w.get("status") == "hit"),
                    key=lambda w: (str(w.get("date", "")), w.get("name", "")))
    return wh, oz, wb, oz_hit


def lead_block(doc):
    _, oz, _, hit = split(doc)
    if not hit:
        return "поражений объектов Ozon в базе проекта не зафиксировано."
    first, last = hit[0]["date"][:10], hit[-1]["date"][:10]
    cities = ", ".join("<strong>%s</strong>" % w["name"] for w in hit[:-1])
    tail = "<strong>%s</strong>" % hit[-1]["name"]
    listing = "%s и %s" % (cities, tail) if cities else tail
    if first == last:
        when = rus_date(first)
    elif first[:7] == last[:7]:          # один месяц — не повторяем его дважды
        when = "с %s по %s" % (first[8:].lstrip("0"), rus_date(last))
    else:
        when = "с %s по %s" % (rus_date(first), rus_date(last))
    burned = [w for w in hit if w.get("damage") == "burned"]
    fire = (" В %s из них сообщается о пожаре." % len(burned)) if 0 < len(burned) < len(hit) else (
        " Во всех эпизодах сообщается о пожаре." if burned else "")
    return ("%s 2026 года сообщалось о поражении %d %s логистики Ozon — %s.%s"
            % (when[0].upper() + when[1:], len(hit),
               plural(len(hit), "объекта", "объектов", "объектов"), listing, fire))


def episodes_block(doc):
    _, _, _, hit = split(doc)
    rows = []
    for w in hit:
        src = w.get("source_url") or ""
        note = (w.get("note") or "").strip() or "логистический объект Ozon"
        link = ('<a href="%s" rel="nofollow noopener" target="_blank">источник ↗</a>' % src) if src else "источник не указан"
        rows.append('        <li><strong>%s</strong> — %s, %s. %s</li>'
                    % (rus_date(w["date"]), w["name"], w.get("region", ""), link))
    if not rows:
        return '      <p class="lead-p">Поражений объектов Ozon в базе проекта нет.</p>'
    return ('      <p class="lead-p">Все эпизоды, внесённые в базу проекта, по датам:</p>\n'
            '      <ul class="lead-p">\n%s\n      </ul>' % "\n".join(rows))


def counts_block(doc):
    wh, oz, wb, hit = split(doc)
    wb_hit = [w for w in wb if w.get("status") == "hit"]
    all_hit = [w for w in wh if w.get("status") == "hit"]
    return ('      <p class="lead-p">На %s 2026 года в базе проекта <strong>%d %s Ozon</strong> из %d '
            'отслеживаемых объектов сети. Для сравнения: у Wildberries поражено %d из %d. Суммарно по складам обоих '
            'маркетплейсов — <strong>%d %s из %d</strong>. Актуальные счётчики и разбивка по операторам — на странице '
            '<a href="/skolko-skladov-wildberries-ozon">«Сколько складов у Wildberries и Ozon»</a>, перечень уцелевших — '
            'в материале <a href="/kakie-sklady-wildberries-ostalis">«Какие склады остались»</a>, эпизоды по датам — '
            'в <a href="/ataki-na-sklady-wildberries-hronika">хронике ударов по складам</a>.</p>'
            % (rus_date(doc["meta"]["generated_at"][:10]), len(hit),
               plural(len(hit), "поражённый объект", "поражённых объекта", "поражённых объектов"),
               len(oz), len(wb_hit), len(wb), len(all_hit),
               plural(len(all_hit), "поражённый объект", "поражённых объекта", "поражённых объектов"), len(wh)))


def faq_answers(doc):
    _, oz, _, hit = split(doc)
    names = ", ".join(w["name"] for w in hit) or "—"
    a_had = ("Да. С %s 2026 года в базе проекта отмечены поражения объектов Ozon: %s. "
             "До 22 августа поражений сети не фиксировалось. Более ранний эпизод 31 июля в Зеленодольске поражением "
             "не был — там прошла только эвакуация." % (rus_date(hit[0]["date"]), names)) if hit else (
        "Поражений объектов Ozon в базе проекта не зафиксировано.")
    a_cnt = ("На %s 2026 года — %d %s из %d отслеживаемых проектом по сети Ozon: %s. Точные счётчики по обеим сетям "
             "приведены в карточках на странице и обновляются вместе с картой."
             % (rus_date(doc["meta"]["generated_at"][:10]), len(hit),
                plural(len(hit), "поражённый объект", "поражённых объекта", "поражённых объектов"),
                len(oz), names))
    return {"Был ли удар по складу Ozon?": a_had,
            "Сколько складов Ozon пострадало?": a_cnt}


def updated_block(doc):
    _, _, _, hit = split(doc)
    n = len(hit)
    return ("Обновлено %s 2026, МСК · %d %s Ozon в базе"
            % (rus_date(doc["meta"]["generated_at"][:10]), n,
               plural(n, "поражённый объект", "поражённых объекта", "поражённых объектов")))


def short_block(doc):
    wh, oz, wb, hit = split(doc)
    wb_hit = [w for w in wb if w.get("status") == "hit"]
    all_hit = [w for w in wh if w.get("status") == "hit"]
    if not hit:
        return '      <p class="lead-p">Поражений объектов Ozon в базе проекта не зафиксировано.</p>'
    return ('      <p class="lead-p">Да, удары были — и не один. С %s 2026 года в базу проекта <code>strikes.json</code>, '
            'куда эпизоды вносятся только после подтверждения открытыми источниками, добавлено <strong>%d %s</strong> '
            'Ozon. До 22 августа их не было ни одного.</p>\n'
            '      <p class="lead-p">Счёт по складам маркетплейсов — <strong>%d из %d</strong>: %d у Wildberries '
            '(из %d в базе) и %d у Ozon (из %d). Это уже не единичный случай, но и не основание для прогнозов: проект '
            'фиксирует подтверждённые события и не предсказывает следующие.</p>'
            % (rus_date(hit[0]["date"]), len(hit),
               plural(len(hit), "поражённый объект", "поражённых объекта", "поражённых объектов"),
               len(all_hit), len(wh), len(wb_hit), len(wb), len(hit), len(oz)))


def cards_block(doc):
    """4 плитки в шапке из данных.

    Были статикой: 26.08 в них стояло свежее число 7, но слово осталось от прошлой
    правки — «7 поражённых ОБЪЕКТА Ozon» вместо «объектов». Числа правили руками,
    согласование — нет. Тот же класс, что и остальные счётчики страницы, поэтому
    плитки тоже уходят под генератор.
    """
    wh, oz, wb, hit = split(doc)
    wb_hit = [w for w in wb if w.get("status") == "hit"]
    all_hit = [w for w in wh if w.get("status") == "hit"]
    days = "—"
    if hit:
        ds = sorted({w["date"][:10] for w in hit if w.get("date")})
        if ds:
            from datetime import date as _d
            a = _d(*(int(x) for x in ds[0].split("-")))
            b = _d(*(int(x) for x in ds[-1].split("-")))
            n = (b - a).days + 1
            days = "%d %s" % (n, plural(n, "день", "дня", "дней"))
    card = ('          <div class="status-card"><div class="val">%s</div>'
            '<div class="lbl">%s</div></div>')
    return "\n".join([
        card % (len(hit), "%s Ozon (из %d)" % (
            plural(len(hit), "поражённый объект", "поражённых объекта",
                   "поражённых объектов"), len(oz))),
        card % (days, "от первого удара до последнего"),
        card % (len(wb_hit), "поражённых складов Wildberries (из %d)" % len(wb)),
        card % (len(all_hit), "поражённых складов в базе (из %d)" % len(wh)),
    ])


def between(html, tag, payload):
    """Замена строго между маркерами — операция идемпотентна."""
    pat = re.compile(r"(<!-- %s:START -->).*?(<!-- %s:END -->)" % (tag, tag), re.S)
    if not pat.search(html):
        raise SystemExit("!! маркер %s не найден в %s" % (tag, os.path.basename(PAGE)))
    return pat.sub(lambda m: m.group(1) + payload + m.group(2), html, count=1)


def set_faq(html, question, answer):
    """Пишем только ВИДИМЫЙ ответ. Разметку пересоберёт sync_faq_ld из него же."""
    vis = re.compile(r'(>%s</div>\s*<div class="faq-a">)(.*?)(</div>)' % re.escape(question), re.S)
    if not vis.search(html):
        raise SystemExit("!! вопрос не найден в видимом FAQ: %s" % question)
    return vis.sub(lambda m: m.group(1) + answer + m.group(3), html, count=1)


def sync_faq_ld(html):
    """FAQPage-разметка пересобирается из видимого текста — единственного источника правды.

    Расхождение разметки с видимым текстом делает её невалидной, и оно накапливается
    незаметно: на этой странице так разошлись 2 ответа из 9, на хронике — 15 из 16.
    Сверять руками бесполезно, поэтому разметка здесь производная, а не параллельная.
    """
    pairs = re.findall(r'class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>', html, re.S)
    if not pairs:
        raise SystemExit("!! видимый FAQ не найден")
    items = []
    for q, a in pairs:
        q_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", q)).strip()
        a_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a)).strip()
        items.append(json.dumps({"@type": "Question", "name": q_txt,
                                 "acceptedAnswer": {"@type": "Answer", "text": a_txt}},
                                ensure_ascii=False))
    block = "      " + ",\n      ".join(items)
    pat = re.compile(r'("@type": "FAQPage",\n    "mainEntity": \[\n).*?(\n    \])', re.S)
    if not pat.search(html):
        raise SystemExit("!! блок FAQPage не найден")
    return pat.sub(lambda m: m.group(1) + block + m.group(2), html, count=1)


def build(html, doc):
    html = between(html, "OZON-LEAD", lead_block(doc))
    html = between(html, "OZON-UPDATED", updated_block(doc))
    html = between(html, "OZON-SHORT", "\n" + short_block(doc) + "\n      ")
    html = between(html, "OZON-EPISODES", "\n" + episodes_block(doc) + "\n      ")
    html = between(html, "OZON-COUNTS", "\n" + counts_block(doc) + "\n      ")
    html = between(html, "OZON-CARDS", "\n" + cards_block(doc) + "\n        ")
    for q, a in faq_answers(doc).items():
        html = set_faq(html, q, a)
    html = sync_faq_ld(html)
    today = doc["meta"]["generated_at"][:10]
    return re.sub(r'("dateModified":\s*")[\d-]+(")', r"\g<1>%s\g<2>" % today, html)


def demo():
    doc = load_data()
    html = build(open(PAGE, encoding="utf8").read(), doc)
    _, oz, _, hit = split(doc)
    assert str(len(hit)) in html and str(len(oz)) in html
    for w in hit:
        assert w["name"] in html, "город %s не попал на страницу" % w["name"]
    assert build(html, doc) == html, "генератор не идемпотентен"
    assert "три поражённых" not in html and "Три эпизода" not in html
    ld = json.loads(re.search(r'"@type": "FAQPage",\n    "mainEntity": \[\n(.*?)\n    \]', html, re.S).group(1).join(["[", "]"]))
    seen = re.findall(r'class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>', html, re.S)
    assert len(ld) == len(seen), "разметка FAQ и видимый текст разошлись по числу вопросов"
    for item, (q, a) in zip(ld, seen):
        assert item["name"] == re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", q)).strip()
        assert item["acceptedAnswer"]["text"] == re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a)).strip()
    assert plural(1, "a", "b", "c") == "a" and plural(3, "a", "b", "c") == "b" and plural(11, "a", "b", "c") == "c"
    assert rus_date("2026-08-22") == "22 августа"
    print("gen-ozon-episodes demo OK — эпизодов: %d, объектов Ozon: %d" % (len(hit), len(oz)))


def main():
    doc = load_data()
    src = open(PAGE, encoding="utf8").read()
    out = build(src, doc)
    if out != src:
        open(PAGE, "w", encoding="utf8").write(out)
        print("udar-po-skladu-ozon.html обновлён по датасету")
    else:
        print("udar-po-skladu-ozon.html — изменений нет")
    return 0


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
