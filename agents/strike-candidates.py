#!/usr/bin/env python3
"""Вариант B: детектор КАНДИДАТОВ в удары по НПЗ/нефтеобъектам из ленты radar-map.ru.

Читает `recent_messages` (агрегированная лента ПВО-мониторинг-каналов с
radar-map.ru — тот же upstream, что и agents/update-radar-state.py), фильтрует
по ключевым словам собственно УДАРА (не просто "опасность/тревога/отбой"),
матчит упомянутый город по справочнику `cities` (координаты оттуда же, как
геокодер), дедуплицирует и пишет data/strike-candidates.json в схеме,
совместимой с data/strikes.json + status:"candidate", confidence:"rumor".

НИКОГДА не публикуется автоматически и НЕ трогает боевой data/strikes.json —
только сырые кандидаты "слух/непроверено" для ручного/Hermes-подтверждения
перед переносом в strikes.json.

Запуск:
  python3 agents/strike-candidates.py              # фетч + запись
  python3 agents/strike-candidates.py --dry-run     # фетч + подсчёт, без записи
Встраивание в Hermes-крон — как соседний скриптовый слой (без claude):
  cd /root/npz-tactical-map && python3 agents/strike-candidates.py && \
    bash agents/git-sync.sh "data(strike-candidates): $(date -u +%Y-%m-%dT%H:%MZ)"
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "strike-candidates.json")
URL = os.environ.get("RADAR_STATE_SOURCE", "https://radar-map.ru/api/state")
UA = "npz-tactical-map-strike-candidates/1.0 (+https://npz-tactical-map.vercel.app/radar)"

# Признак собственно УДАРА (прилёт/детонация/пожар...), НЕ просто сигнал тревоги.
STRIKE_RE = re.compile(r"прилет|прилёт|взрыв|пожар|горит|загор|поражен|детонац|удар по", re.IGNORECASE)
# Признак цели — топливный/промышленный объект.
TARGET_RE = re.compile(r"нпз|нефтезавод|нефтеперерабат|нефтебаз|нефтехранил|терминал|завод|\bнб\b", re.IGNORECASE)


def fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_strike_candidate(text):
    """True, если сообщение похоже на УДАР по объекту (не просто тревога/отбой)."""
    return bool(text) and bool(STRIKE_RE.search(text)) and bool(TARGET_RE.search(text))


def matched_target_keyword(text):
    m = TARGET_RE.search(text or "")
    return m.group(0) if m else ""


_RU_SOFT_ENDINGS = "ьйаеиоуыэюя"


def _city_pattern(name):
    """Русские топонимы склоняются («в Сызрани» от «Сызрань»), точное совпадение
    слова их не ловит. Для имён длиннее 4 букв матчим по стему (без последней
    буквы) + любое окончание; короткие имена — точным словом, чтобы не хватать
    случайные подстроки."""
    if len(name) <= 4:
        return r"\b" + re.escape(name) + r"\b"
    stem = name[:-1] if name[-1].lower() in _RU_SOFT_ENDINGS else name
    return r"\b" + re.escape(stem) + r"[а-яёА-ЯЁ]*"


def geocode_city(text, cities):
    """Ищет упоминание города из справочника cities (radar-map.ru) в тексте.
    Берёт самое длинное совпадение имени, чтобы короткие имена не перекрывали
    более специфичные (напр. «Ялта» внутри «Приялтинский»)."""
    best = None
    for c in cities:
        name = (c.get("name") or "").strip()
        if not name or len(name) < 3:
            continue
        if re.search(_city_pattern(name), text, re.IGNORECASE):
            if best is None or len(name) > len(best.get("name", "")):
                best = c
    return best


def to_candidate(msg, city):
    ts = msg.get("ts")
    utc = dt.datetime.fromtimestamp(ts, dt.timezone.utc) if ts else dt.datetime.now(dt.timezone.utc)
    msk = utc + dt.timedelta(hours=3)
    kw = matched_target_keyword(msg.get("text", ""))
    city_name = city.get("name") if city else ""
    region = city.get("region") if city else ""
    return {
        "date": utc.strftime("%Y-%m-%d"),
        "time": utc.strftime("%H:%M"),
        "time_local": msk.strftime("%H:%M МСК"),
        "city": city_name,
        "region": region,
        "lat": city.get("lat") if city else None,
        "lon": city.get("lon") if city else None,
        "type": "неизвестно",
        "count": None,
        "target": ("объект уточняется (по тексту: %s)" % kw) if kw else "объект уточняется",
        "casualties": "неизвестно",
        "title": ("Возможный удар по объекту в %s" % city_name) if city_name else "Возможный удар (город не определён)",
        "detail": (msg.get("text") or "").strip()[:400],
        "source_url": None,
        "confidence": "rumor",
        "status": "candidate",
        "msg_id": msg.get("msg_id"),
        "source_label": msg.get("source_label"),
        "source_id": msg.get("source_id"),
        "geocoded": city is not None,
    }


def collect_candidates(payload):
    cities = payload.get("cities") or []
    if isinstance(cities, dict):  # на случай уже сконвертированного dict-формата
        cities = list(cities.values())
    messages = payload.get("recent_messages") or payload.get("feed") or []
    out = []
    for msg in messages:
        text = msg.get("text") or ""
        if not is_strike_candidate(text):
            continue
        city = geocode_city(text, cities)
        out.append(to_candidate(msg, city))
    return out


def merge(existing, new):
    """Идемпотентный мерж: не плодит дубли по msg_id и по паре (город, дата)."""
    seen_ids = {str(c.get("msg_id")) for c in existing if c.get("msg_id") is not None}
    seen_city_date = {(c.get("city"), c.get("date")) for c in existing if c.get("city")}
    merged = list(existing)
    added = 0
    for c in new:
        mid = str(c.get("msg_id")) if c.get("msg_id") is not None else None
        cd = (c.get("city"), c.get("date")) if c.get("city") else None
        if mid and mid in seen_ids:
            continue
        if cd and cd in seen_city_date:
            continue
        merged.append(c)
        added += 1
        if mid:
            seen_ids.add(mid)
        if cd:
            seen_city_date.add(cd)
    return merged, added


def load_existing():
    if os.path.exists(OUT):
        try:
            return json.load(open(OUT, encoding="utf-8")).get("candidates", [])
        except Exception:
            return []
    return []


def demo():
    """Самопроверка фильтра/геокодера — без сети."""
    assert is_strike_candidate("Прилёт по НПЗ в Сызрани, пожар на территории завода") is True
    assert is_strike_candidate("Взрыв и пожар на нефтебазе") is True
    assert is_strike_candidate("Опасность БПЛА в Брянской области") is False
    assert is_strike_candidate("Брянская область\nОтбой опасности по БПЛА") is False
    assert is_strike_candidate("Курская область\nвнимание по бпла") is False

    fake_cities = [{"name": "Сызрань", "region": "Самарская область", "lat": 53.15, "lon": 48.47}]
    city = geocode_city("Прилёт по НПЗ в Сызрани, пожар", fake_cities)
    assert city and city["name"] == "Сызрань"

    cand = to_candidate({"msg_id": 1, "text": "Прилёт по НПЗ в Сызрани, пожар", "ts": 1783498594,
                         "source_label": "test", "source_id": "test"}, city)
    assert cand["status"] == "candidate" and cand["confidence"] == "rumor" and cand["city"] == "Сызрань"

    # идемпотентность: второй прогон с тем же msg_id не плодит дубль
    merged1, added1 = merge([], [cand])
    merged2, added2 = merge(merged1, [cand])
    assert added1 == 1 and added2 == 0 and len(merged2) == 1

    print("[self-check] OK: фильтр, геокодер и дедуп работают корректно")


def main():
    demo()
    dry_run = "--dry-run" in sys.argv
    try:
        payload = fetch_json(URL)
    except Exception as exc:
        print("strike-candidates: ERROR fetching %s: %s" % (URL, exc), file=sys.stderr)
        sys.exit(1)

    feed = payload.get("recent_messages") or payload.get("feed") or []
    new_candidates = collect_candidates(payload)
    existing = load_existing()
    merged, added = merge(existing, new_candidates)

    print("strike-candidates: %d сообщений в ленте, %d похожи на удар, %d новых (после дедупа), всего в файле %d" % (
        len(feed), len(new_candidates), added, len(merged)))

    if dry_run:
        print("--dry-run: не сохраняю")
        return

    now = dt.datetime.now(dt.timezone.utc)
    out = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%MZ"),
        "data_mode": "СЛУХ / НЕПРОВЕРЕНО (вариант B)",
        "disclaimer": "Авто-детектор кандидатов в удары из ленты radar-map.ru. НЕ боевые данные, НЕ публикуется автоматически. Только для ручного/Hermes-подтверждения перед переносом в strikes.json.",
        "candidates": merged,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT)
    print("WROTE %s: %d кандидатов" % (OUT, len(merged)))


if __name__ == "__main__":
    main()
