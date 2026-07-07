#!/usr/bin/env python3
"""Watchdog: читает generated_at всех живых data/*.json, сравнивает с порогом
(≈2× cron-интервала агента) и пишет data/health.json. Если файл просрочен —
помечает stale. Фронт может показать «N агентов отстали». Запуск из cron-рутины.

Поддержка heartbeat: если data/heartbeats.json существует, для каждого файла
считается heartbeat_age_hours и статус уточняется:
  ok          — данные свежи
  stale_alive — данные просрочены, но heartbeat свеж (агент работал, просто нет новостей)
  stale_dead  — данные просрочены и heartbeat просрочен/отсутствует (агент мёртв)
  unknown     — generated_at не найден
"""
import json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# файл -> (агент, порог свежести данных в часах, heartbeat-key, порог свежести heartbeat в часах).
# heartbeat-key совпадает с label в run-agent.sh.
# hb_fresh_h — per-agent окно «жив» (≈2× cron-интервала + буфер). КРИТИЧНО для редких рутин:
# глобальные 72ч ложно «убивали» недельный forecast-economy в середине недели.
# Статичные файлы (azs-*, geojson) не проверяем.
WATCH = {
    "strikes.json":           ("npz-data (strikes)",   18, "strikes",          72),
    "fuel-state.json":        ("npz-data (npz)",        24, "npz-status",       72),
    "history-crimea.json":    ("npz-data (history)",    36, "history-crimea",   72),
    "roads.json":             ("npz-data (roads)",      36, "roads",            72),
    "fuel-availability.json": ("fuel-availability",     18, "fuel-availability",72),
    "fuel-voices.json":       ("fuel-voices",           24, "fuel-voices",      72),
    "grid-state.json":        ("grid-status",           18, "grid-status",      72),
    "radar-state.json":       ("radar-state",          0.5, "radar-state",       2),
    # forecast-economy — НЕДЕЛЬНАЯ рутина (cron вс 03:45): окно «жив» = 200ч (>1 недели + буфер).
    "forecast.json":          ("forecast-economy",     200, "forecast",        200),
    "economy.json":           ("forecast-economy",     200, "economy",         200),
}

# Дефолт для агентов, по которым per-file порог не задан.
HEARTBEAT_FRESHNESS_HOURS = 72


def gen_at(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    m = d.get("meta", {})
    ts = m.get("generated_at") or d.get("generated_at") or d.get("fetched_at") or d.get("last_event_at")
    if ts:
        return ts
    raw_ts = d.get("timestamp")
    if isinstance(raw_ts, (int, float)):
        return datetime.datetime.fromtimestamp(raw_ts, datetime.timezone.utc).isoformat()
    return d.get("date")


def parse(ts):
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        pass
    try:
        return datetime.datetime.strptime(str(ts)[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def load_heartbeats():
    path = os.path.join(ROOT, "data", "heartbeats.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    heartbeats = load_heartbeats()
    files = []
    stale_count = 0
    dead_count = 0
    hb_dead_count = 0
    for fn, (agent, thr_h, hb_key, hb_fresh_h) in WATCH.items():
        ts = gen_at(os.path.join(ROOT, "data", fn))
        dt = parse(ts)
        if dt is None:
            status, data_age_h = "unknown", None
        else:
            # Клипуем отрицательный возраст: cloud-агент может писать generated_at
            # на минуты впереди часов watchdog (clock skew) — это не «будущее».
            data_age_h = max(0.0, round((now - dt).total_seconds() / 3600, 1))
            status = "ok" if data_age_h <= thr_h else "stale"

        hb_ts = heartbeats.get(hb_key)
        hb_dt = parse(hb_ts)
        if hb_dt is None:
            hb_age_h = None
        else:
            hb_age_h = max(0.0, round((now - hb_dt).total_seconds() / 3600, 1))

        # per-agent окно heartbeat (см. WATCH): редкие рутины не «умирают» ложно.
        if status == "stale":
            if hb_age_h is not None and hb_age_h <= hb_fresh_h:
                status = "stale_alive"
            else:
                status = "stale_dead"
                dead_count += 1

        if status in ("stale", "stale_dead", "stale_alive"):
            stale_count += 1

        # Liveness is orthogonal to data freshness: a producer agent can be dead
        # (heartbeat stale/missing) while its data still looks fresh because a bulk
        # commit bumped generated_at. Surface that separately (does NOT gate overall).
        hb_stale = hb_age_h is None or hb_age_h > hb_fresh_h
        if hb_stale:
            hb_dead_count += 1

        files.append({
            "file": fn, "agent": agent, "generated_at": ts,
            "age_hours": data_age_h, "data_age_hours": data_age_h,
            "threshold_hours": thr_h,
            "heartbeat_at": hb_ts, "heartbeat_age_hours": hb_age_h,
            "heartbeat_threshold_hours": hb_fresh_h,
            "heartbeat_stale": hb_stale,
            "status": status,
        })

    health = {
        "meta": {
            # Контракт (docs/heartbeat-plan.md): overall=degraded ТОЛЬКО при dead_count>0
            # (агент не дал данных И heartbeat протух). heartbeat_dead_count —
            # информационный сигнал, он НЕ должен сам по себе валить overall.
            "checked_at": now.strftime("%Y-%m-%dT%H:%MZ"),
            "overall": "degraded" if dead_count else "healthy",
            "stale_count": stale_count,
            "dead_count": dead_count,
            "heartbeat_dead_count": hb_dead_count,
            "total": len(WATCH),
        },
        "files": files,
    }
    out = os.path.join(ROOT, "data", "health.json")
    json.dump(health, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("health: %s | stale %d/%d | dead %d | hb_dead %d" % (
        health["meta"]["overall"], stale_count, len(WATCH), dead_count, hb_dead_count))
    for f in files:
        if f["status"] != "ok":
            print("  ⚠ %s (%s): %s, data_age=%s h, hb_age=%s h" % (
                f["file"], f["agent"], f["status"],
                f["age_hours"], f["heartbeat_age_hours"]))
        elif f["heartbeat_stale"]:
            print("  💀 %s (%s): data ok but heartbeat DEAD, data_age=%s h, hb_age=%s h" % (
                f["file"], f["agent"],
                f["age_hours"], f["heartbeat_age_hours"]))


if __name__ == "__main__":
    main()
