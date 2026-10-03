#!/usr/bin/env python3
"""Карточки /npz/*.html: title/H1 под интент «<завод> работает или нет» + блок ответа
первым экраном из data/fuel-state.json (между маркерами CARD-STATUS).

Зачем (23.09.2026): в Вебмастере растут запросы «нпз капотня работает или нет»,
«ярославский нпз работает или нет» (CTR 13–25%), а карточки держали датированные
title вида «удар БПЛА 10 июня» и статус, застывший на июле (Куйбышевский стоит с
22.09, карточка «обновлена 9 июля»). /npz/kinef с ответом первой строкой — самая
посещаемая карточка. Обещать «работает или нет» можно только с честным ответом ниже.

Блок без даты «на сегодня» — меняется только при смене статуса, без ежедневного
перекоммита 33 файлов. Идемпотентен. Запуск: python3 agents/gen-npz-card-status.py
Самопроверка без записи: --demo.
"""
import importlib.util
import json
import os
import re
import sys
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "agents", fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


REF = _load("gen_refineries", "gen-refineries.py")      # CARDS, state_phrase
NAV = _load("build_nav", "build-nav.py")                # LABELS: имя завода для меню

START, END = "<!-- CARD-STATUS:START -->", "<!-- CARD-STATUS:END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)


# Имя для title/H1 — поисковая форма, а не подпись меню: люди ищут «ярославский нпз
# работает или нет», а не «НПЗ ЯНОС»; у /npz/kinef прежний title «Киришский НПЗ (КИНЕФ)»
# держал самую посещаемую карточку — не терять.
SEARCH_NAMES = {
    "kinef": "Киришский НПЗ (КИНЕФ)",
    "slavneft-yanos": "Ярославский НПЗ (ЯНОС)",
    "lukojl-norsi": "Кстовский НПЗ (Лукойл-НОРСИ)",
    "lukojl-permnefteorgsintez": "Пермский НПЗ (Лукойл-Пермнефтеоргсинтез)",
    "salavat-npz": "Салаватский НПЗ (Газпром нефтехим Салават)",
    "ns-oil": "Новоспасский НПЗ (NS-Oil)",
}


def label(slug):
    return SEARCH_NAMES.get(slug) or NAV.LABELS[f"/npz/{slug}"][1]


def block(r, name):
    phrase = REF.state_phrase(r)
    load = " (выработка 0%)" if r["status"] == "down" else ""  # у partial процент уже в state_phrase
    src = (r.get("source_url") or "").strip()
    src_a = f' Источник: <a href="{escape(src)}" rel="nofollow noopener" target="_blank">открытая публикация ↗</a>.' if src.startswith("http") else ""
    return (f'{START}\n<p class="lead-p card-status"><strong>Работает ли {escape(name)} сейчас?</strong> '
            f'По оценке открытых источников — <strong>{escape(phrase)}</strong>{load}.{src_a} '
            f'Статус всех 33 заводов — <a href="/rabotayut-li-npz-rossii">какие НПЗ работают сейчас</a>.</p>\n{END}')


def faq_answer(r):
    """Ответ на «Работает ли … сейчас?» — из данных, а не застывший июльский текст
    (03.10.2026: карточки писали «около 40%» про заводы, стоящие с сентября)."""
    phrase = REF.state_phrase(r)
    if r["status"] == "down":
        head, tail = "Нет", f"завод {phrase} (оценка выработки 0%)"
    elif r["status"] == "partial":
        pct, ss = r.get("est_output_pct"), r.get("status_since")
        when = f" с {REF.rus_date(ss)}" if ss else ""
        head = "Частично"
        tail = f"завод работает примерно на {pct}% мощности{when}" if pct is not None else f"завод {phrase}"
    else:
        head, tail = "Да", f"завод {phrase}"
    return (f"{head}. По оценке открытых источников, {tail}. Статус меняется после новых ударов "
            f"и ремонтов — актуальная отметка в начале страницы и на карте НПЗ.")


def descriptions(r, name):
    """meta description (до ~160 знаков) и короткий og/twitter — из текущего статуса."""
    phrase = REF.state_phrase(r)
    load = " (выработка 0%)" if r["status"] == "down" else ""
    st = phrase[0].upper() + phrase[1:] + load
    cap = f"{r['capacity_mt_year']:g}".replace(".", ",")
    op = (r.get("operator") or "").strip()
    if op and op.split()[0].lower() in name.lower():   # «Марийский НПЗ, Марийский НПЗ» — не повторять
        op = ""
    facts = f"{op}, {cap} млн т/год".lstrip(", ")
    meta = f"{name} работает или нет: {phrase}{load}. {facts}. Хроника ударов БПЛА и влияние на рынок топлива."
    if len(meta) > 175:
        meta = f"{name} работает или нет: {phrase}{load}. {facts}. Хроника ударов БПЛА."
    og = f"{st}. {facts}. Хроника ударов БПЛА и статус переработки."
    return meta, og


def _set_meta(html, attr, val):
    return re.sub(r'(<meta ' + re.escape(attr) + r' content=")[^"]*(")',
                  lambda m: m.group(1) + escape(val) + m.group(2), html, count=1)


VIS_Q = re.compile(r'(<div class="faq-q">Работает ли[^<]*</div>\s*<div class="faq-a">)(.*?)(</div>)', re.S)
LD_Q = re.compile(r'("name":\s*"Работает ли[^"]*",\s*"acceptedAnswer":\s*\{"@type":\s*"Answer",\s*"text":\s*")((?:[^"\\]|\\.)*)(")')
DM = re.compile(r'("dateModified":\s*")(\d{4}-\d{2}-\d{2})(")')


FACT_OUT = re.compile(r'(<span class="fact-num">)[^<]*(</span>\s*<span class="fact-label">)[^<]*выработк[^<]*(</span>)')
STATUS_SEC = re.compile(r'(<section[^>]*id="status".*?</section>)', re.S)
TILE_STATE = re.compile(r'(<span class="status-tile-state)(?: [a-z-]+)?(">)[^<]*(</span>)')
TILE_NOTE = re.compile(r'(<div class="status-tile-note">).*?(</div>)', re.S)
TILE_CLS = {"down": "dry", "partial": "limited", "operational": "ok"}


def output_fact(r):
    pct, ss = r.get("est_output_pct"), r.get("status_since")
    when = f" (с {REF.rus_date(ss)})" if ss and r["status"] != "operational" else ""
    num = "0%" if r["status"] == "down" else f"~{pct}%" if r["status"] == "partial" and pct is not None else "100%"
    return num, f"оценка выработки{when}"


def tile_note(r):
    """Повреждения из данных: первые предложения до ~320 знаков, без обрыва на полуслове."""
    dmg = re.sub(r"\s+", " ", (r.get("damage") or "").strip())
    if not dmg:
        return "По данным открытых источников, сведений о повреждениях нет."
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", dmg):
        if out and len(out) + len(sent) > 320:
            break
        out = (out + " " + sent).strip()
    return out


def render(html, r, slug):
    name = label(slug)
    title = f"{name} работает или нет сегодня: статус завода и удары БПЛА"
    h1 = f"{name}: работает или нет — статус завода и хроника ударов"
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.S)
    for attr in ('property="og:title"', 'name="twitter:title"'):
        html = re.sub(r'(<meta ' + re.escape(attr) + r' content=")[^"]*(")', lambda m: m.group(1) + escape(title) + m.group(2), html, count=1)
    html = re.sub(r'("headline": ")[^"]*(")', lambda m: m.group(1) + title.replace('"', '\\"') + m.group(2), html, count=1)
    html = re.sub(r"(<h1[^>]*>).*?(</h1>)", lambda m: m.group(1) + escape(h1) + m.group(2), html, count=1, flags=re.S)
    meta, og = descriptions(r, name)
    html = _set_meta(html, 'name="description"', meta)
    html = _set_meta(html, 'property="og:description"', og)
    html = _set_meta(html, 'name="twitter:description"', og)
    ans = faq_answer(r)
    html = VIS_Q.sub(lambda m: m.group(1) + escape(ans, quote=False) + m.group(3), html, count=1)
    html = LD_Q.sub(lambda m: m.group(1) + json.dumps(ans, ensure_ascii=False)[1:-1] + m.group(3), html, count=1)
    num, lab = output_fact(r)
    html = FACT_OUT.sub(lambda m: m.group(1) + num + m.group(2) + lab + m.group(3), html, count=1)
    st = REF.state_phrase(r)
    st = st[0].upper() + st[1:]
    def _tile(m):
        sec = TILE_STATE.sub(lambda t: f'{t.group(1)} {TILE_CLS[r["status"]]}{t.group(2)}{escape(st)}{t.group(3)}', m.group(1), count=1)
        if r["status"] == "operational" and not (r.get("damage") or "").strip():
            return sec   # штатный завод без повреждений: ручная справка о заводе ценнее заглушки
        return TILE_NOTE.sub(lambda t: t.group(1) + escape(tile_note(r), quote=False) + t.group(2), sec, count=1)
    html = STATUS_SEC.sub(_tile, html, count=1)
    ss = r.get("status_since") or ""
    # dateModified только вперёд: дата смены статуса, не «сегодня» — без ежедневного перекоммита
    html = DM.sub(lambda m: m.group(1) + max(m.group(2), ss[:10]) + m.group(3), html)
    b = block(r, name)
    if BLOCK_RE.search(html):
        html = BLOCK_RE.sub(lambda m: b, html, count=1)
    else:
        html = re.sub(r"(<h1[^>]*>.*?</h1>)", lambda m: m.group(1) + "\n" + b, html, count=1, flags=re.S)
    return html


def main(write=True):
    R = json.load(open(os.path.join(ROOT, "data", "fuel-state.json"), encoding="utf-8"))["refineries"]
    changed = 0
    for r in R:
        slug = REF.CARDS.get(r["id"])
        path = os.path.join(ROOT, "npz", f"{slug}.html") if slug else None
        if not path or not os.path.exists(path):
            print(f"!! нет карточки для {r['id']}", file=sys.stderr)
            continue
        html = open(path, encoding="utf-8").read()
        new = render(html, r, slug)
        if new != html:
            changed += 1
            if write:
                open(path, "w", encoding="utf-8").write(new)
    print(f"gen-npz-card-status: карточек изменено {changed}")
    return changed


def demo():
    r = {"id": "x", "operator": "Роснефть", "capacity_mt_year": 7.0, "status": "down", "est_output_pct": 0, "status_since": "2026-09-22", "source_url": "https://e.org/a"}
    page = ('<meta name="description" content="старое 40%"><meta property="og:description" content="о"><meta name="twitter:description" content="т">'
            '"dateModified": "2026-07-09", "name": "Работает ли завод сейчас?", "acceptedAnswer": {"@type": "Answer", "text": "около 40% \\"x\\""}'
            '<div class="faq-q">Работает ли завод сейчас?</div>\n<div class="faq-a">около 40%</div>')
    page += ('<span class="fact-num">~40%</span>\n<span class="fact-label">оценка выработки (на 16 июля 2026)</span>'
             '<section class="n" id="status"><span class="status-tile-state limited">Снижена</span><div class="status-tile-note">около 40%</div></section>')
    r["damage"] = "Удар 22 сентября. Повреждена АВТ."
    page += '<title>Старый</title><meta property="og:title" content="o"><meta name="twitter:title" content="t">"headline": "h",<h1 class="x">Старый H1</h1><p>тело</p>'
    NAV.LABELS["/npz/demo"] = ("🛢️", "Куйбышевский НПЗ (Самара)")
    once = render(page, r, "demo")
    assert "Куйбышевский НПЗ (Самара) работает или нет сегодня" in once
    assert "остановлен с 22 сентября 2026" in once and "выработка 0%" in once, once
    assert once.count(START) == 1 and once.index(START) > once.index("</h1>")
    assert render(once, r, "demo") == once, "не идемпотентен"
    assert "40%" not in once, "застывший ответ/description не перезаписан"
    assert once.count("Нет. По оценке открытых источников, завод остановлен с 22 сентября 2026") == 2, once
    assert '"dateModified": "2026-09-22"' in once
    assert '<span class="fact-num">0%</span>' in once and "оценка выработки (с 22 сентября 2026)" in once, once
    assert 'status-tile-state dry">Остановлен с 22 сентября 2026<' in once and "status-tile-note\">Удар 22 сентября. Повреждена АВТ.<" in once, once
    assert render(once, dict(r, status_since="2026-08-01"), "demo").count('"dateModified": "2026-09-22"') == 1, "dateModified не должен откатываться"
    json.loads('{"t": "' + LD_Q.search(once).group(2) + '"}')
    r2 = dict(r, status="partial", est_output_pct=40)
    assert "Частично. По оценке открытых источников, завод работает примерно на 40% мощности с 22 сентября 2026." in render(once, r2, "demo")
    assert "работает на ~40%" in render(once, r2, "demo") and render(once, r2, "demo").count(START) == 1
    print("demo OK")


if __name__ == "__main__":
    demo() if "--demo" in sys.argv else main()
