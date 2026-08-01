#!/usr/bin/env python3
"""Молния уходит в зеркало АНОНИМНЫМ ботом, и падение зеркала не рушит основной канал.

Три инварианта:
  1. Основной канал (@NPZmap) получает молнию как раньше — личным ботом (api_call).
  2. Зеркало (@npz_karta_online) получает ТУ ЖЕ молнию, но через
     channel_mirror._telegram_call с АНОНИМНЫМ токеном — НЕ через api_call()
     личного бота. Эта путаница уже случалась (коммит 2340dd31 подключил
     зеркало молнии через api_call, т.е. личным ботом — деанон); тест ловит
     именно это, сравнивая токен, а не просто факт вызова.
  3. Падение зеркала (или отсутствие токена) НЕ должно ронять публикацию
     в основной канал.

Запуск: python3 test_molniya_mirror.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_CHANNEL_MIRRORS", "@test_mirror")

import radar_publish as RP
import channel_mirror as CM
import day_state as DS

STRIKE = {"id": "test-mirror-1", "date": "2026-08-01", "time": "04:00",
          "city": "Тестоград", "region": "Тестовая область",
          "target": "Тестовый НПЗ", "source_url": "https://example.org/x"}

ANON_TOKEN = "ANON-TOKEN-SENTINEL"


def run(fail_mirror=False, no_mirror_token=False):
    """Подменяет отправку в основной канал (RP.api_call) и в зеркало
    (CM._telegram_call / CM.mirror_token) РАЗДЕЛЬНО, чтобы поймать смешение
    личного и анонимного бота, а не просто факт «зеркало вызвалось»."""
    channel_calls = []
    mirror_calls = []

    def fake_api(method, **kw):
        channel_calls.append(str(kw.get("chat_id")))
        return {"ok": True, "result": {"message_id": len(channel_calls)}}

    def fake_telegram_call(token, method, **kw):
        mirror_calls.append((token, str(kw.get("chat_id"))))
        if fail_mirror:
            return {"ok": False, "description": "Bad Request: chat not found"}
        return {"ok": True, "result": {"message_id": 999}}

    orig_api, orig_subs, orig_load, orig_save = (
        RP.api_call, RP._get_active_subscribers, DS.load_state, DS.save_state)
    orig_telegram_call, orig_mirror_token = CM._telegram_call, CM.mirror_token

    RP.api_call = fake_api
    RP._get_active_subscribers = lambda: []
    CM._telegram_call = fake_telegram_call
    CM.mirror_token = (lambda: None) if no_mirror_token else (lambda: ANON_TOKEN)
    state = DS.ensure_today(None, DS.today_iso())
    DS.load_state = lambda: state
    DS.save_state = lambda s: None
    try:
        return RP.publish_strike_molniya(dict(STRIKE)), channel_calls, mirror_calls
    finally:
        (RP.api_call, RP._get_active_subscribers,
         DS.load_state, DS.save_state) = orig_api, orig_subs, orig_load, orig_save
        CM._telegram_call, CM.mirror_token = orig_telegram_call, orig_mirror_token


# 1+2: основной канал личным ботом, зеркало — анонимным
res, channel_calls, mirror_calls = run()
assert RP.CHANNEL_CHAT_ID in channel_calls, "молния не ушла в основной канал: %s" % channel_calls
assert mirror_calls, "молния не ушла в зеркало"
assert mirror_calls[0][1] == "@test_mirror", "зеркало ушло не в тот чат: %s" % (mirror_calls[0],)
assert mirror_calls[0][0] == ANON_TOKEN, (
    "🔴 зеркало ушло НЕ анонимным токеном (%r) — деанон бот в @npz_karta_online" % (mirror_calls[0][0],))
assert res["channel_ok"] is True

# 3: падение зеркала не должно ронять основной канал
res, channel_calls, mirror_calls = run(fail_mirror=True)
assert res["channel_ok"] is True, "🔴 падение зеркала уронило основной канал"
assert RP.CHANNEL_CHAT_ID in channel_calls

# нет токена зеркала -> зеркало молча пропускается, основной канал не страдает
res, channel_calls, mirror_calls = run(no_mirror_token=True)
assert res["channel_ok"] is True
assert not mirror_calls, "нет токена зеркала — зеркало не должно было вызываться: %s" % mirror_calls

print("test_molniya_mirror: ok")
