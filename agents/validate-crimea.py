#!/usr/bin/env python3
"""Валидатор схемы данных history-crimea.json.
Запуск: python3 agents/validate-crimea.py [--today YYYY-MM-DD]"""
import json, sys, os, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_RE = re.compile(r"^https?://")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


ok = True
warnings = []


def err(m):
    global ok
    ok = False
    print("FAIL:", m)


def warn(m):
    warnings.append(m)
    print("WARN:", m)


def validate(data, today_override=None):
    global ok, warnings
    ok = True
    warnings = []

    # --- crimea block required ---
    crimea = data.get("crimea")
    if not isinstance(crimea, dict):
        err("crimea: missing or not an object")
        return

    # --- restrictions[] ---
    for i, r in enumerate(crimea.get("restrictions", [])):
        if isinstance(r, str):
            continue
        if not isinstance(r, dict):
            err(f"restrictions[{i}]: expected str or dict, got {type(r).__name__}")
            continue
        text = r.get("text", "")
        if not isinstance(text, str) or not text.strip():
            err(f"restrictions[{i}]: text is empty or missing")
        d = r.get("date")
        if d is not None:
            if not isinstance(d, str) or not DATE_RE.match(d):
                err(f"restrictions[{i}]: date malformed: {d!r}")
        u = r.get("source_url")
        if u is not None:
            if not isinstance(u, str) or not URL_RE.match(u):
                err(f"restrictions[{i}]: source_url malformed: {u!r}")

    # --- stations[] ---
    stations = crimea.get("stations", [])
    if not stations:
        err("stations: empty or missing")
    for i, s in enumerate(stations):
        name = s.get("name")
        if not isinstance(name, str) or not name.strip():
            err(f"stations[{i}]: name empty or missing")
        status = s.get("status")
        if not isinstance(status, str) or not status.strip():
            err(f"stations[{i}]: status empty or missing")
        note = s.get("note")
        if note is not None and not isinstance(note, str):
            err(f"stations[{i}]: note must be str if present")

    # --- freshness warning ---
    dates_found = []
    for s in stations:
        # stations don't have date fields; pull from restrictions instead
        pass
    for r in crimea.get("restrictions", []):
        if isinstance(r, dict) and r.get("date"):
            dates_found.append(r["date"])
    if data.get("generated_at"):
        dates_found.append(data["generated_at"])

    if dates_found:
        newest = max(dates_found)
        if today_override:
            try:
                delta = (datetime.strptime(today_override, "%Y-%m-%d") - datetime.strptime(newest, "%Y-%m-%d")).days
            except ValueError:
                delta = 0
            if delta > 10:
                warn(f"Данные устарели: последняя дата {newest}, сегодня {today_override} ({delta} дней)")
        else:
            print(f"INFO: новейшая дата в данных — {newest} (--today не задан, сверка пропущена)")


def demo():
    """Самотестирование: валидный и невалидный образцы."""
    good = {
        "generated_at": "2026-07-08",
        "crimea": {
            "summary": "test",
            "stations": [
                {"name": "Симферополь", "status": "dry", "note": "ok"},
                {"name": "Керчь", "status": "limited"},
            ],
            "restrictions": [
                {"date": "2026-07-08", "text": "тест", "source_url": "https://example.com"},
                "просто строка",
            ],
        },
    }
    validate(good)
    assert ok, "demo good should pass"

    bad = {
        "generated_at": "2026-07-08",
        "crimea": {
            "summary": "test",
            "stations": [
                {"name": "", "status": "dry"},
            ],
            "restrictions": [
                {"date": "bad-date", "text": "", "source_url": "not-a-url"},
            ],
        },
    }
    validate(bad)
    assert not ok, "demo bad should fail"

    print("demo() OK — self-check passed")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
        sys.exit(0)

    today = None
    for i, a in enumerate(sys.argv):
        if a == "--today" and i + 1 < len(sys.argv):
            today = sys.argv[i + 1]

    path = os.path.join(ROOT, "data", "history-crimea.json")
    if not os.path.exists(path):
        print("FAIL: файл не найден:", path)
        sys.exit(1)

    data = load(path)
    validate(data, today)

    if ok:
        n_stations = len(data.get("crimea", {}).get("stations", []))
        n_restrictions = len(data.get("crimea", {}).get("restrictions", []))
        print(f"OK crimea data valid ({n_stations} stations, {n_restrictions} restrictions)")
    else:
        print("INVALID")

    if warnings:
        print(f"\n{len(warnings)} warning(s)")

    sys.exit(0 if ok else 1)
