#!/usr/bin/env python3
"""Сторож /lab/world: свежесть рядов, индекс, очередь. Без LLM.

  watch.py [--dry-run] [--notify] [--data DIR] [--state P]

Печатает JSON {ok, problems[]}. --notify: одно сообщение владельцу, не чаще раза в 6 ч
на тот же набор проблем (состояние data/world/.watch-state.json). --dry-run: сообщение
печатается, состояние не пишется. В incidents.md ничего не пишет.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

FREQ_DAYS = {"daily": 1, "weekly": 7, "monthly": 31}
# публикационный лаг источников (FRED ~4 дня, PortWatch ~7): нижний порог для дневных рядов
MIN_LIMIT_DAYS = {"daily": 9}
INDEX_MAX_H = 8
MIN_COVERAGE = 0.5
QUEUE_STALE_H = 48
ANTIFLAP_H = 6
REMIND_H = 24


def _hours(now, ts):
    d = C.parse_ts(ts)
    return None if d is None else (now - d).total_seconds() / 3600


def find_problems(series, index, queue, now, state=None):
    """-> список {key, text}. Ключ стабилен: по нему считается анти-дребезг."""
    state = state or {}
    out = []
    for sid, s in sorted((series or {}).get("series", {}).items()):
        if s.get("error") and s.get("value") is None:
            out.append({"key": f"series:{sid}:error", "text": f"ряд {sid}: ошибка источника ({s['error']})"})
            continue
        limit = max(FREQ_DAYS.get(s.get("freq"), 7) * 2, MIN_LIMIT_DAYS.get(s.get("freq"), 0))
        if s.get("stale_days"):
            limit = max(limit, int(s["stale_days"]))  # порог источника из collect.py (IEA: лаг ~100 дн.)
        d = C.parse_ts(s.get("as_of"))
        age = (now.date() - d.date()).days if d else None
        if age is None or age > limit:
            out.append({"key": f"series:{sid}:stale",
                        "text": f"ряд {sid}: устарел (as_of {s.get('as_of')}, лимит {limit} дн.)"})
        elif s.get("error"):
            out.append({"key": f"series:{sid}:error", "text": f"ряд {sid}: {s['error']}"})
    h = _hours(now, (index or {}).get("generated_at"))
    if h is None:
        out.append({"key": "index:missing", "text": "index.json отсутствует или без generated_at"})
    elif h > INDEX_MAX_H:
        out.append({"key": "index:old", "text": f"index.json старше {INDEX_MAX_H} ч ({h:.0f} ч)"})
    cov = ((index or {}).get("world") or {}).get("coverage")
    if cov is not None and cov < MIN_COVERAGE:
        out.append({"key": "index:coverage", "text": f"coverage мира {cov} < {MIN_COVERAGE}"})
    old = []
    for c in (queue or {}).get("candidates", []):
        if c.get("verdict") == "ready":
            hh = _hours(now, c.get("found_at") or c.get("notified_at"))
            if hh is not None and hh > QUEUE_STALE_H:
                old.append(c.get("id"))
    if old:
        last = _hours(now, state.get("queue_reminded_at"))
        if last is None or last >= REMIND_H:
            out.append({"key": "queue:stale", "text": f"{len(old)} ready без решения >48 ч: " + ", ".join(old[:8])})
    return out


def run(data_dir, state_path, notify=False, dry=False, send=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    series = C.load_json(os.path.join(data_dir, "series.json"), {})
    index = C.load_json(os.path.join(data_dir, "index.json"), {})
    queue = C.load_json(os.path.join(data_dir, "events-queue.json"), {})
    state = C.load_json(state_path, {})
    problems = find_problems(series, index, queue, now, state)
    result = {"ok": not problems, "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "problems": [p["text"] for p in problems], "notified": False}
    if problems and notify:
        sig = hashlib.sha1("|".join(sorted(p["key"] for p in problems)).encode()).hexdigest()
        last = _hours(now, state.get("sent_at")) if state.get("sig") == sig else None
        if last is None or last >= ANTIFLAP_H:
            text = ("Сергей, это ИИ-ассистент. Сторож /lab/world нашёл проблемы:\n- "
                    + "\n- ".join(result["problems"]))
            if dry:
                print(text, file=sys.stderr)
            else:
                if send is None:
                    import notify as N
                    send = N.tg_send
                if send(text):
                    result["notified"] = True
                    state.update(sig=sig, sent_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    if any(p["key"] == "queue:stale" for p in problems):
                        state["queue_reminded_at"] = state["sent_at"]
                    C.write_json_atomic(state_path, state)
        else:
            result["suppressed"] = "анти-дребезг: тот же набор <6 ч назад"
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--data", default=C.D)
    ap.add_argument("--state", default=None)
    a = ap.parse_args(argv)
    r = run(a.data, a.state or os.path.join(a.data, ".watch-state.json"), a.notify, a.dry_run)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
