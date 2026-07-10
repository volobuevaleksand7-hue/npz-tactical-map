#!/usr/bin/env python3
"""Строит data/search-index.json — статический индекс для search.js (без бэкенда, без сети).

Источники (три, как в реестре):
  1) data/seo-topics.jsonl — статьи/регионы/страницы НПЗ (title из primary_kw, url, keywords, type)
  2) data/strikes.json — уникальные города ударов → ссылка на регион-страницу, если для региона
     удара есть подходящая страница (Крым/Краснодар/Москва/ракетная-опасность-*), иначе на "/"
  3) refineries.html — полная таблица НПЗ (28 заводов); те, что уже есть как отдельная
     страница (type=object в реестре), получают свою ссылку, остальные — на /refineries

Идемпотентно: `python3 agents/build-search-index.py` перезаписывает data/search-index.json.
Self-check: `python3 agents/build-search-index.py --check`.
"""
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEO_FILE = ROOT / "data" / "seo-topics.jsonl"
STRIKES_FILE = ROOT / "data" / "strikes.json"
REFINERIES_HTML = ROOT / "refineries.html"
OUT_FILE = ROOT / "data" / "search-index.json"

GROUP_BY_TYPE = {"region": "Города", "object": "НПЗ"}
DEFAULT_GROUP = "Статьи"

# region-страница по подстроке в поле region удара (порядок важен: Крым/Севастополь
# перед Краснодарским краем, т.к. в данных встречается "Республика Крым / Краснодарский край").
# ponytail: ручная карта на ~10 известных региональных страниц, не гео-геокодер.
REGION_MAP = [
    ("крым", "/crimea"),
    ("севастополь", "/crimea"),
    ("краснодарский край", "/krasnodar"),
    ("московская обл", "/raketnaya-opasnost-moskovskaya-oblast"),
    ("волгоградская обл", "/raketnaya-opasnost-volgograd"),
    ("чуваш", "/raketnaya-opasnost-cheboksary"),
    ("омская обл", "/raketnaya-opasnost-omsk"),
    ("ульяновская обл", "/raketnaya-opasnost-ulyanovsk"),
    ("татарстан", "/raketnaya-opasnost-kazan"),
    ("пензенская обл", "/raketnaya-opasnost-penza"),
    ("самарская обл", "/raketnaya-opasnost-samara"),
]

REFINERY_TABLE_RE = re.compile(
    r'<table class="refinery-table">.*?</table>', re.DOTALL
)
REFINERY_ROW_RE = re.compile(
    r'<tr><td>(?:<a href="([^"]+)">)?([^<]+?)(?:</a>)?</td>'
    r'<td>([^<]*)</td><td>([^<]*)</td>'
)


def norm(s):
    return (s or "").lower().replace("ё", "е")


def region_url(city, region):
    if (city or "").strip() == "Москва":
        return "/moskva"
    hay = norm(region)
    for needle, url in REGION_MAP:
        if needle in hay:
            return url
    return "/"


def load_seo():
    rows = []
    if not SEO_FILE.exists():
        return rows
    for line in SEO_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("status") != "live":
            continue
        kw = d.get("primary_kw") or d["url"]
        title = kw[:1].upper() + kw[1:]
        rows.append({
            "title": title,
            "url": d["url"],
            "group": GROUP_BY_TYPE.get(d.get("type"), DEFAULT_GROUP),
            "keywords": d.get("keywords", []),
        })
    return rows


def load_strike_cities():
    rows = []
    if not STRIKES_FILE.exists():
        return rows
    data = json.loads(STRIKES_FILE.read_text(encoding="utf-8"))
    seen = set()
    for s in data.get("strikes", []):
        city = (s.get("city") or "").strip()
        if not city or city in seen:
            continue
        seen.add(city)
        region = s.get("region") or ""
        rows.append({
            "title": city,
            "url": region_url(city, region),
            "group": "Удары",
            "keywords": [region] if region else [],
        })
    return rows


def load_refineries():
    rows = []
    if not REFINERIES_HTML.exists():
        return rows
    html = REFINERIES_HTML.read_text(encoding="utf-8")
    table_m = REFINERY_TABLE_RE.search(html)
    if not table_m:
        return rows
    seen = set()
    for m in REFINERY_ROW_RE.finditer(table_m.group(0)):
        url, name, operator, region = m.groups()
        name = name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append({
            "title": name,
            "url": url or "/refineries",
            "group": "НПЗ",
            "keywords": [operator.strip(), region.strip()],
        })
    return rows


def build():
    entries = []
    seen_key = set()

    def add_all(rows):
        for r in rows:
            key = (r["title"].lower(), r["url"])
            if key in seen_key:
                continue
            seen_key.add(key)
            text = norm(" ".join([r["title"], r["group"], " ".join(r["keywords"])]))
            entries.append({
                "title": r["title"],
                "url": r["url"],
                "group": r["group"],
                "keywords": r["keywords"],
                "text": text,
            })

    # порядок важен для дедупа: страницы из реестра (более точный title) — первыми,
    # затем удары, затем полная таблица НПЗ (дозаполняет заводы без отдельной страницы)
    add_all(load_seo())
    add_all(load_strike_cities())
    add_all(load_refineries())

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "entries": entries,
    }


def main():
    if "--check" in sys.argv:
        if not OUT_FILE.exists():
            print("FAIL: data/search-index.json не найден — запусти без --check сначала")
            sys.exit(1)
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        entries = data.get("entries", [])
        assert entries, "индекс пуст"
        bad = [e["url"] for e in entries if not e.get("url", "").startswith("/")]
        assert not bad, f"url без ведущего / : {bad[:5]}"
        groups = sorted(set(e["group"] for e in entries))
        print(f"OK: {len(entries)} записей, группы: {groups}")
        return

    data = build()
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_group = {}
    for e in data["entries"]:
        by_group[e["group"]] = by_group.get(e["group"], 0) + 1
    print(f"Записано {data['count']} записей → {OUT_FILE.relative_to(ROOT)}")
    for g, n in sorted(by_group.items()):
        print(f"  {g}: {n}")


if __name__ == "__main__":
    main()
