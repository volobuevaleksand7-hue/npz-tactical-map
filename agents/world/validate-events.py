#!/usr/bin/env python3
"""Детерминированный валидатор очереди кандидатов /lab/world (без LLM).

  python3 agents/world/validate-events.py [--dry] [--queue P] [--events P]
                                          [--no-net] [--workers N] [--timeout S]

Для каждого кандидата пишет checks{schema,urls_alive,neutral_lexicon,independent_sources}
и verdict ready|needs_source|rejected (+reject_reason). Сеть недоступна -> urls_alive
"unknown", не reject. confirmed без двух независимых издателей (strike/seizure/
attack_shipping) понижается до reported. --dry: только печать, файл не трогается.
"""
import argparse
import difflib
import importlib.util
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

try:
    import neutrality as NEU  # agents/neutrality.py
except Exception:  # noqa: BLE001
    NEU = None

LOCAL_SLUR = ("терорист", "террорист", "русня", "кацап", "москал", "хохл", "слава украин",
              "доблестн", "возмездие", "героическ")
TEXT_FIELDS = ("title", "summary", "fuel_effect")
EN_FIELDS = ("title_en", "summary_en", "fuel_effect_en")


def translation_warning(c):
    """Мягкая проверка английской версии: -> строка-предупреждение или None. Verdict не меняет."""
    miss = [f for f in EN_FIELDS if not (isinstance(c.get(f), str) and c.get(f).strip())]
    # fuel_effect_en не нужен, если fuel_effect пуст
    if not c.get("fuel_effect") and "fuel_effect_en" in miss:
        miss.remove("fuel_effect_en")
    if miss:
        return "warning: нет " + ", ".join(miss)
    bad = [f for f in EN_FIELDS if isinstance(c.get(f), str) and set(c[f].lower()) & set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")]
    if bad:
        return "warning: кириллица в " + ", ".join(bad)
    return None


def check_schema(c, today=None):
    """-> список ошибок схемы (пусто = ок)."""
    errs = []
    today = today or C.today()
    for k in ("id", "occurred_at", "type", "region", "status", "title", "summary", "sources"):
        if c.get(k) in (None, "", []):
            errs.append(f"нет поля {k}")
    if c.get("type") not in C.TYPES:
        errs.append(f"type '{c.get('type')}' вне enum")
    if c.get("region") not in C.REGIONS:
        errs.append(f"region '{c.get('region')}' вне enum")
    if c.get("status") not in C.STATUSES:
        errs.append(f"status '{c.get('status')}' вне enum")
    lat, lon = c.get("lat"), c.get("lon")
    if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not -90 <= lat <= 90:
        errs.append("lat вне -90..90")
    if not isinstance(lon, (int, float)) or isinstance(lon, bool) or not -180 <= lon <= 180:
        errs.append("lon вне -180..180")
    if c.get("precision") not in ("point", "zone"):
        errs.append("precision не point|zone")
    d = C.parse_ts(c.get("occurred_at"))
    if d is None:
        errs.append("occurred_at не дата")
    else:
        age = (today - d.date()).days
        if age < 0:
            errs.append("дата из будущего")
        elif age > C.MAX_AGE_DAYS:
            errs.append(f"старше {C.MAX_AGE_DAYS} дней")
    srcs = c.get("sources")
    if not isinstance(srcs, list) or not srcs:
        errs.append("нет источников")
    else:
        for s in srcs:
            if not isinstance(s, dict) or not str(s.get("url", "")).startswith(("http://", "https://")):
                errs.append("источник без http(s) URL")
                break
            if not s.get("publisher"):
                errs.append("источник без publisher")
                break
    ph = c.get("photo")
    if ph is not None and (not isinstance(ph, dict) or not ph.get("license")):
        errs.append("photo без license")
    return errs


def lexicon_problems(c):
    out = []
    for f in TEXT_FIELDS:
        t = c.get(f)
        if not isinstance(t, str):
            continue
        if NEU is not None:
            out += [f"{f}: {r[0]}" for r in NEU.text_reasons(t)]
        low = t.lower()
        if set(t) & set("іїєґ") and not any(x.startswith(f"{f}: UA") for x in out):
            out.append(f"{f}: UA-lang")
        if not any(x.startswith(f"{f}: slogan") for x in out):
            out += [f"{f}: slogan ({w})" for w in LOCAL_SLUR if w in low][:1]
    return out


def url_alive(url, timeout=10):
    """True / False / None (сеть недоступна -> unknown)."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "Mozilla/5.0 world-lab-validator"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return 200 <= r.status < 400
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 400, 501):
                continue
            return 200 <= e.code < 400
        except (urllib.error.URLError, OSError, TimeoutError):
            if method == "HEAD":
                continue
            return None
    return None


def check_urls(cands, workers=4, timeout=10, fetch=url_alive):
    urls = sorted({s["url"] for c in cands for s in (c.get("sources") or [])
                   if isinstance(s, dict) and s.get("url")})
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        res = dict(zip(urls, ex.map(lambda u: fetch(u, timeout), urls)))
    return res


def haversine_km(a, b):
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def is_duplicate(c, other):
    if c.get("id") and c.get("id") == other.get("id"):
        return True
    d1, d2 = C.parse_ts(c.get("occurred_at")), C.parse_ts(other.get("occurred_at"))
    if not d1 or not d2 or abs((d1.date() - d2.date()).days) > 2:
        return False
    sim = difflib.SequenceMatcher(None, str(c.get("title", "")).lower(),
                                  str(other.get("title", "")).lower()).ratio()
    if sim >= 0.8:
        return True
    try:
        near = haversine_km((c["lat"], c["lon"]), (other["lat"], other["lon"])) < 30
    except Exception:  # noqa: BLE001
        near = False
    return near and c.get("type") == other.get("type") and sim >= 0.5


def validate(cands, existing, url_results=None, today=None):
    """Мутирует кандидатов (checks/verdict). url_results: {url: True|False|None} или None."""
    seen = list(existing)
    for c in cands:
        reasons, needs = [], False
        errs = check_schema(c, today)
        lex = lexicon_problems(c)
        c["checks"] = {"schema": "ok" if not errs else "fail: " + "; ".join(errs),
                       "urls_alive": "unknown",
                       "neutral_lexicon": "ok" if not lex else "fail: " + "; ".join(lex),
                       "independent_sources": 0}
        tw = translation_warning(c)
        c["checks"]["translation"] = tw or "ok"
        if errs:
            reasons.append("schema")
        if lex:
            reasons.append("lexicon")
        srcs = [s for s in (c.get("sources") or []) if isinstance(s, dict)]
        if url_results is not None and srcs:
            vals = [url_results.get(s.get("url")) for s in srcs]
            if any(v is False for v in vals):
                c["checks"]["urls_alive"] = "fail"
                reasons.append("dead_url")
            elif all(v is True for v in vals):
                c["checks"]["urls_alive"] = "ok"
        n = C.independent_count(srcs)
        c["checks"]["independent_sources"] = n
        if c.get("status") == "confirmed" and c.get("type") in C.NEED_TWO and n < 2:
            c["status"] = "reported"
            c["checks"]["downgraded"] = "confirmed->reported: <2 независимых издателей"
        if c.get("type") in C.NEED_TWO and n < 2:
            needs = True
        dup = next((o for o in seen if o is not c and is_duplicate(c, o)), None)
        if dup:
            reasons.append("duplicate:" + str(dup.get("id")))
        if reasons:
            c["verdict"], c["reject_reason"] = "rejected", ", ".join(reasons)
        elif needs:
            c["verdict"], c["reject_reason"] = "needs_source", "нужен второй независимый издатель"
        else:
            c["verdict"], c["reject_reason"] = "ready", None
        seen.append(c)
    return cands


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--queue", default=C.QUEUE)
    ap.add_argument("--events", default=C.EVENTS)
    ap.add_argument("--no-net", action="store_true", help="не проверять URL")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args(argv)
    q = C.load_json(a.queue, {"generated_at": None, "candidates": []})
    ev = C.load_json(a.events, {"events": []}).get("events", [])
    cands = q.get("candidates", [])
    # уже одобренные/отклонённые не пересматриваем
    todo = [c for c in cands if c.get("verdict") != "approved" and not c.get("decided_at")]
    urls = None if a.no_net else check_urls(todo, a.workers, a.timeout)
    if urls and all(v is None for v in urls.values()):
        urls = {k: None for k in urls}  # сеть недоступна: unknown
    validate(todo, ev + [c for c in cands if c not in todo], urls)
    q["validated_at"] = C.now_iso()
    summary = {v: sum(1 for c in cands if c.get("verdict") == v) for v in ("ready", "needs_source", "rejected")}
    print(json.dumps({"checked": len(todo), **summary, "dry": a.dry}, ensure_ascii=False))
    if a.dry:
        for c in todo:
            print(" ", c.get("id"), c.get("verdict"), c.get("reject_reason") or "")
        return 0
    C.write_json_atomic(a.queue, q)
    return 0


if __name__ == "__main__":
    sys.exit(main())
