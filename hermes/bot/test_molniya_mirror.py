#!/usr/bin/env python3
"""Молния уходит в зеркало, и падение зеркала не рушит основной канал.

Второе важнее первого: зеркало — необязательный канал, и если Telegram ответит по нему
ошибкой, @NPZmap всё равно обязан получить молнию. Запуск: python3 test_molniya_mirror.py
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_CHANNEL_MIRRORS", "@test_mirror")

import radar_publish as RP
import day_state as DS

STRIKE = {"id": "test-mirror-1", "date": "2026-08-01", "time": "04:00",
          "city": "Тестоград", "region": "Тестовая область",
          "target": "Тестовый НПЗ", "source_url": "https://example.org/x"}


def run(fail_on):
    """Подменяет отправку: собирает адресатов, роняет тех, кто в fail_on."""
    calls = []
    orig_api, orig_subs, orig_load, orig_save = (
        RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state)

    def fake_api(method, **kw):
        calls.append(str(kw.get("chat_id")))
        if str(kw.get("chat_id")) in fail_on:
            return {"ok": False, "description": "Bad Request: chat not found"}
        return {"ok": True, "result": {"message_id": len(calls)}}

    RP.api_call = fake_api
    RP._get_active_subscribers = lambda: []
    state = DS.ensure_today(None, DS.today_iso())
    DS.load_state = lambda: state
    DS.save_state = lambda s: None
    try:
        return RP.publish_strike_molniya(dict(STRIKE)), calls
    finally:
        (RP.api_call, RP._get_active_subscribers,
         DS.load_state, DS.save_state) = orig_api, orig_subs, orig_load, orig_save


res, calls = run(fail_on=set())
assert RP.CHANNEL_CHAT_ID in calls, "молния не ушла в основной канал: %s" % calls
assert "@test_mirror" in calls, "молния не ушла в зеркало: %s" % calls
assert res["channel_ok"] is True

res, calls = run(fail_on={"@test_mirror"})
assert res["channel_ok"] is True, "🔴 падение зеркала уронило основной канал"
assert any("mirror" in e for e in res["errors"]), res["errors"]

print("test_molniya_mirror: ok")
