#!/usr/bin/env python3
"""Стадия СБОРА трипвайра: внешние каналы (реестр agents/sources.json) → кандидаты
в удары в общее озеро data/strike-candidates.json (confidence:"rumor").

Первый источник — YouTube-канал Newsader через публичную RSS-ленту
(https://www.youtube.com/feeds/videos.xml?channel_id=...), которая работает
headless БЕЗ авторизации (в отличие от yt-dlp, который на VPS ловит бот-чек).
Фильтрует заголовки по ключам-целям (топливо/суда/мосты/энерго), геокодит город
по справочнику radar-map.ru, дедуплицирует по videoId и (город,дата) и МЕРЖИТ в
то же озеро, что и agents/strike-candidates.py (radar). Дальше — общая труба:
ручное/Hermes-подтверждение → strikes.json → сводка. В strikes.json НЕ вливается.

ponytail: одно озеро, atomic-write, дедуп по merge() из strike-candidates.
Гонка при одновременной записи с radar-кроном закрыта разносом минут в кроне;
если станет узким местом — отдельный файл на источник + merge на чтении.

Запуск:
  python3 agents/collect.py            # self-check + фетч + мерж-запись
  python3 agents/collect.py --dry-run   # фетч + подсчёт, без записи
Крон (VPS), со сдвигом от radar-кандидатов (:20):
  5 */1 * * * cd /root/npz-tactical-map && python3 agents/collect.py && \
    bash agents/git-sync.sh "data(collect): $(date -u +%Y-%m-%dT%H:%MZ)"
"""
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "agents")
SOURCES = os.path.join(AGENTS, "sources.json")
OUT = os.path.join(ROOT, "data", "strike-candidates.json")
RADAR_STATE = os.environ.get("RADAR_STATE_SOURCE", "https://radar-map.ru/api/state")
UA = "npz-tactical-map-collect/1.0 (+https://npz-tactical-map.vercel.app/radar)"
RSS_TMPL = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

# Переиспользуем геокодер/мерж из strike-candidates.py (в имени дефис → importlib).
_sc_path = os.path.join(AGENTS, "strike-candidates.py")
_spec = importlib.util.spec_from_file_location("strike_candidates", _sc_path)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

# Цели канала шире топливных (суда/мосты/энерго). Наличие цели в заголовке —
# главный фильтр: отсекает интервью/политику ("Лариса Волошина…", "Зеленский…").
TARGET_RE = re.compile(
    r"нпз|нефтезавод|нефтеперераб|нефтебаз|нефтехранил|нефтетермин|нефтеналив|нефтепровод|"
    r"терминал|топлив|бензин|\bгсм\b|"
    r"танкер|судн|суда|\bфлот|порт\b|"
    r"мост|"
    r"энергообъект|энергомост|подстанц|\bгрэс\b|\bтэц\b|электро|"
    r"\bвпк\b|\bзавод|склад", re.IGNORECASE)
# Глаголы удара — только для матч-кейворда в target (не как обязательный фильтр).
STRIKE_KW = re.compile(
    r"удар|горит|разгор|загор|пожар|пыла|взрыв|взорв|поражен|детонац|сожгл|сожж|"
    r"сгорел|уничтож|снесл|разгром|прилет|прилёт", re.IGNORECASE)


def fetch_rss(channel_id):
    req = urllib.request.Request(RSS_TMPL % channel_id, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall("a:entry", ATOM_NS):
        vid = e.find("yt:videoId", ATOM_NS)
        title = e.find("a:title", ATOM_NS)
        pub = e.find("a:published", ATOM_NS)
        if vid is None or title is None:
            continue
        out.append({"id": vid.text, "title": title.text or "",
                    "published": pub.text if pub is not None else None})
    return out


def matched_target(text):
    m = TARGET_RE.search(text or "")
    return m.group(0).lower() if m else ""


def _parse_iso(s):
    if not s:
        return dt.datetime.now(dt.timezone.utc)
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def to_candidate(entry, src, city):
    utc = _parse_iso(entry.get("published"))
    msk = utc + dt.timedelta(hours=3)
    kw = matched_target(entry["title"])
    city_name = city.get("name") if city else ""
    return {
        # дата = дата ЗАГРУЗКИ ролика (может быть на сутки позже ночного удара —
        # Гермес уточняет при подтверждении). ponytail: точнее не нужно для rumor.
        "date": utc.strftime("%Y-%m-%d"),
        "time": utc.strftime("%H:%M"),
        "time_local": msk.strftime("%H:%M МСК"),
        "city": city_name,
        "region": city.get("region") if city else "",
        "lat": city.get("lat") if city else None,
        "lon": city.get("lon") if city else None,
        "type": "неизвестно",
        "count": None,
        "target": ("объект уточняется (по тексту: %s)" % kw) if kw else "объект уточняется",
        "casualties": "неизвестно",
        # НЕЙТРАЛЬНЫЙ title — кликбейт канала сюда НЕ копируем.
        "title": ("Сигнал об ударе — %s" % city_name) if city_name else "Сигнал об ударе (город уточняется)",
        "detail": ("[%s] %s" % (src["label"], (entry["title"] or "").strip()))[:400],
        "source_url": "https://www.youtube.com/watch?v=%s" % entry["id"],
        "confidence": "rumor",
        "status": "candidate",
        "msg_id": entry["id"],            # videoId — ключ дедупа, не пересекается с числовыми radar msg_id
        "source_label": src["label"],
        "source_id": src["id"],
        "geocoded": city is not None,
    }


def collect(sources, cities, dry=False):
    out = []
    for src in sources:
        if not src.get("enabled") or src.get("type") != "youtube_rss":
            continue
        try:
            entries = fetch_rss(src["channel_id"])
        except Exception as exc:
            print("collect: ERROR RSS %s: %s" % (src["id"], exc), file=sys.stderr)
            continue
        hit = 0
        for e in entries:
            if not TARGET_RE.search(e["title"] or ""):
                continue
            city = sc.geocode_city(e["title"], cities)
            out.append(to_candidate(e, src, city))
            hit += 1
        print("collect: %s — %d видео, %d похожи на удар" % (src["id"], len(entries), hit))
    return out


def load_full():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    return {"generated_at": "", "data_mode": "СЛУХ / НЕПРОВЕРЕНО (вариант B)",
            "disclaimer": "Авто-детектор кандидатов в удары. НЕ боевые данные, НЕ публикуется автоматически.",
            "candidates": []}


def demo():
    """Self-check фильтра/маппинга — без сети."""
    assert TARGET_RE.search("ПЫЛАЮТ НЕФТЕБАЗЫ В ТВЕРИ")
    assert TARGET_RE.search("ВСУ ВЗЯЛИСЬ ЗА МОСТЫ")
    assert TARGET_RE.search("Ильский НПЗ снова горит")
    assert not TARGET_RE.search("Лариса Волошина: НАТО открыло новую эпоху")
    assert not TARGET_RE.search("ЗЕЛЕНСКИЙ В УДАРЕ: встречи с конгрессменами")
    fake = [{"name": "Тверь", "region": "Тверская область", "lat": 56.86, "lon": 35.9}]
    c = to_candidate({"id": "abc123", "title": "ПЫЛАЮТ НЕФТЕБАЗЫ В ТВЕРИ", "published": "2026-07-11T19:00:00+00:00"},
                     {"id": "newsader", "label": "Newsader"}, sc.geocode_city("ПЫЛАЮТ В ТВЕРИ", fake))
    assert c["status"] == "candidate" and c["confidence"] == "rumor"
    assert c["source_url"].endswith("abc123") and c["msg_id"] == "abc123"
    assert "нефтебаз" in c["target"] and c["city"] == "Тверь"
    # дедуп по videoId идемпотентен
    m1, a1 = sc.merge([], [c]); m2, a2 = sc.merge(m1, [c])
    assert a1 == 1 and a2 == 0 and len(m2) == 1
    print("[self-check] OK: фильтр, маппинг, дедуп")


def main():
    demo()
    dry = "--dry-run" in sys.argv
    try:
        payload = sc.fetch_json(RADAR_STATE)
        cities = payload.get("cities") or []
    except Exception as exc:
        print("collect: WARN нет справочника городов (%s) — гео пропущено" % exc, file=sys.stderr)
        cities = []

    sources = json.load(open(SOURCES, encoding="utf-8")).get("sources", [])
    new = collect(sources, cities)
    doc = load_full()
    merged, added = sc.merge(doc.get("candidates", []), new)
    geo = sum(1 for c in new if c.get("geocoded"))
    print("collect: %d кандидатов (%d с гео), %d новых после дедупа, всего %d" % (
        len(new), geo, added, len(merged)))

    if dry:
        print("--dry-run: не сохраняю")
        return
    doc["candidates"] = merged
    doc["generated_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)
    print("WROTE %s: %d кандидатов (+%d)" % (OUT, len(merged), added))


if __name__ == "__main__":
    main()
