#!/usr/bin/env python3
"""Контентный слой /karta-bpla: последние события + перелинковка регионов.

Проблема реопта (см. docs/agents/seo, кластер «карта бпла»): первый экран —
iframe /radar?embed=1, поисковику почти нечего читать. Этот генератор
штампует под iframe видимый текст из тех же данных, что и сама карта —
data/strikes.json (10 последних событий) и data/seo-topics.jsonl (список
живых страниц /raketnaya-opasnost-*), — чтобы через 2 дня страница не врала.

Маркеры в karta-bpla.html: <!-- GEN:recent-events --> / <!-- GEN:region-links -->
(тот же паттерн splice(), что в agents/gen-refineries.py).

Вызов — hermes/publish-vps.sh, тем же неблокирующим шагом, что gen-refineries.py
и gen-npz-status-page.py (страж «написан, но не подключён» — главная грабля
проекта, см. CLAUDE.md).

  python3 agents/gen-karta-bpla-events.py           # перегенерить + записать
  python3 agents/gen-karta-bpla-events.py --check   # только проверить, не писать
  python3 agents/gen-karta-bpla-events.py --selftest
"""
import argparse
import html
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "karta-bpla.html"
STRIKES = ROOT / "data" / "strikes.json"
TOPICS = ROOT / "data" / "seo-topics.jsonl"

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

TYPE_LABEL = {"missile": "Ракета", "both": "БПЛА и ракета"}  # остальное -> "БПЛА"


def rus_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {RU_MONTHS[m - 1]} {y}"


def splice(text, name, body):
    """Заменить содержимое между <!-- GEN:name --> и <!-- /GEN:name -->
    (тот же паттерн, что agents/gen-refineries.py:splice)."""
    pat = re.compile(rf"(<!-- GEN:{name} -->\n?).*?(\n?\s*<!-- /GEN:{name} -->)", re.S)
    if not pat.search(text):
        sys.exit(f"нет маркеров GEN:{name} в {PAGE.name}")
    return pat.sub(lambda m: m.group(1) + body + m.group(2), text)


def render_events(strikes, n=10):
    last = strikes[-n:][::-1]  # новые сверху
    rows = []
    for s in last:
        date = s.get("date", "")
        try:
            d = rus_date(date)
        except Exception:
            d = date
        region = s.get("region") or s.get("city") or "—"
        ttype = TYPE_LABEL.get(s.get("type"), "БПЛА")
        short = s.get("target") or s.get("detail") or ""
        short = short.strip()
        if len(short) > 90:
            short = short[:87].rstrip() + "…"
        rows.append(
            f'<div class="ev-item"><span class="ev-date">{html.escape(d)}</span> · '
            f'<span class="ev-region">{html.escape(region)}</span> · '
            f'<span class="ev-type">{html.escape(ttype)}</span> · '
            f'{html.escape(short)}</div>'
        )
    return "\n".join(rows)


def _load_cities():
    """Имена/регионы городов — берём из agents/gen-rocket-danger.py (CITIES),
    чтобы не заводить второй словарь тех же 15 городов."""
    spec = importlib.util.spec_from_file_location("_grd", ROOT / "agents" / "gen-rocket-danger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CITIES


def render_region_links():
    cities = _load_cities()
    by_slug = {c["slug"]: c for c in cities.values()}
    live_slugs = []
    for line in TOPICS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        url = rec.get("url", "")
        if rec.get("type") == "region" and url.startswith("/raketnaya-opasnost-") and rec.get("status") == "live":
            live_slugs.append(url.lstrip("/"))
    cards = []
    for slug in live_slugs:
        c = by_slug.get(slug)
        nom = c["nom"] if c else slug
        region = c["region"] if c else ""
        cards.append(
            f'<a class="link-card" href="/{slug}"><div class="lc-h">📍 {html.escape(nom)}</div>'
            f'<div class="lc-d">Мониторинг БПЛА и ракетной опасности{" · " + html.escape(region) if region and region != nom else ""}</div></a>'
        )
    return "\n".join(cards)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="только проверить, не писать")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    strikes = json.loads(STRIKES.read_text(encoding="utf-8"))["strikes"]
    events_html = render_events(strikes)
    links_html = render_region_links()

    text = PAGE.read_text(encoding="utf-8")
    new_text = splice(text, "recent-events", events_html)
    new_text = splice(new_text, "region-links", links_html)

    if a.check:
        if new_text != text:
            sys.exit("дрейф: karta-bpla.html не совпадает с данными — прогони без --check")
        print("check OK — карта БПЛА согласована с данными")
        return

    PAGE.write_text(new_text, encoding="utf-8")
    print(f"karta-bpla.html: {len(events_html.splitlines())} событий, "
          f"{links_html.count('link-card')} регион-ссылок")


def selftest():
    html_in = "x<!-- GEN:recent-events -->\nOLD\n<!-- /GEN:recent-events -->y"
    out = splice(html_in, "recent-events", "NEW")
    assert out == "x<!-- GEN:recent-events -->\nNEW\n<!-- /GEN:recent-events -->y", out

    strikes = [{"date": "2026-09-16", "region": "Ростовская область", "type": "drone",
                "target": "нефтебаза"}]
    ev = render_events(strikes, n=10)
    assert "16 сентября 2026" in ev and "Ростовская область" in ev and "БПЛА" in ev, ev
    print("selftest OK")


if __name__ == "__main__":
    main()
