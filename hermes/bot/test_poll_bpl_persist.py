#!/usr/bin/env python3
"""Регресс на баг «настройки не сохраняются» (Task 1): интервал/тумблеры/регионы
должны переживать перезагрузку subscribers.json. Воспроизводит логику хендлеров
poll_bpl (load_subs → ensure_sub(subs=subs) → mutate → save_subs) без Telegram.

Требует, чтобы был импортируем telegram (запускать в venv VPS):
  NPZ_BPL_DIR=$(mktemp -d) /root/hermes-stack/hermes/.venv/bin/python3 test_poll_bpl_persist.py
"""
import json
import os
import sys
import tempfile

os.environ["NPZ_BPL_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poll_bpl as P  # noqa: E402


def reload_alerts(cid):
    with open(os.path.join(os.environ["NPZ_BPL_DIR"], "subscribers.json"), encoding="utf-8") as f:
        return json.load(f)["subscribers"][cid]["alerts"]


def set_interval(cid, val):  # как on_timer_callback / cmd_interval
    subs = P.load_subs()
    sub = P.ensure_sub(cid, "", subs=subs)
    sub["alerts"]["interval_min"] = val
    P.save_subs(subs)


def toggle(cid, field):  # как on_alerts_callback
    subs = P.load_subs()
    sub = P.ensure_sub(cid, "", subs=subs)
    alerts = sub.setdefault("alerts", {})
    alerts[field] = not alerts.get(field, True)
    P.save_subs(subs)


def test_interval_persists():
    set_interval("42", 30)
    assert reload_alerts("42")["interval_min"] == 30, "интервал не сохранился"
    set_interval("42", 10)
    assert reload_alerts("42")["interval_min"] == 10
    print("ok: interval persists")


def test_toggle_persists():
    toggle("42", "attacks")
    assert reload_alerts("42")["attacks"] is False, "тумблер attacks не сохранился"
    toggle("42", "attacks")
    assert reload_alerts("42")["attacks"] is True
    toggle("42", "threats")
    assert reload_alerts("42")["threats"] is False
    print("ok: toggle persists")


def test_regions_still_work():
    P.set_sub_regions("42", ["Москва"])
    assert reload_alerts("42")["regions"] == ["Москва"], "регресс: регионы"
    print("ok: regions (no regression)")


if __name__ == "__main__":
    test_interval_persists()
    test_toggle_persists()
    test_regions_still_work()
    print("\nAll poll_bpl persistence tests passed.")
