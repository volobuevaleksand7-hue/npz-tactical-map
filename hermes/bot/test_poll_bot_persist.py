#!/usr/bin/env python3
"""Регресс на баг «настройки не сохраняются» для @NpzFuel_Bot (poll_bot.py):
интервал/регионы должны переживать перезагрузку subscribers.json.
Воспроизводит логику хендлеров (load_subs → ensure_sub(subs=subs) → mutate → save_subs).
Запускать в venv VPS (нужен импорт telegram):
  NPZ_BOT_DIR=$(mktemp -d) /root/hermes-stack/hermes/.venv/bin/python3 test_poll_bot_persist.py
"""
import json
import os
import sys
import tempfile

os.environ["NPZ_BOT_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poll_bot as P  # noqa: E402


def reload_alerts(cid):
    with open(os.path.join(os.environ["NPZ_BOT_DIR"], "subscribers.json"), encoding="utf-8") as f:
        return json.load(f)["subscribers"][cid]["alerts"]


def set_interval(cid, val):  # как on_timer_callback / cmd_interval
    subs = P.load_subs()
    sub = P.ensure_sub(cid, "", subs=subs)
    sub["alerts"]["interval_min"] = val
    P.save_subs(subs)


def test_interval_persists():
    set_interval("77", 30)
    assert reload_alerts("77")["interval_min"] == 30, "интервал не сохранился"
    set_interval("77", 10)
    assert reload_alerts("77")["interval_min"] == 10
    print("ok: interval persists")


def test_regions_still_work():
    P.set_sub_regions("77", ["Москва"])
    assert reload_alerts("77")["regions"] == ["Москва"], "регресс: регионы"
    print("ok: regions (no regression)")


if __name__ == "__main__":
    test_interval_persists()
    test_regions_still_work()
    print("\nAll poll_bot persistence tests passed.")
