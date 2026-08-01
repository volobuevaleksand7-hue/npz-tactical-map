#!/usr/bin/env python3
"""channel_mirror.py — общий хелпер зеркалирования @NPZmap -> @npz_karta_online.

Зеркала постит ОТДЕЛЬНЫЙ анонимный бот (@npz_karta_bot, токен в
NPZ_MIRROR_TOKEN), НЕ личный @NpzFuel_Bot — тот заведён с аккаунта владельца,
его админка в анонимном канале означала бы деанон проекта (уже была такая
ошибка — молния в зеркало уходила через api_call() личного бота, коммит
2340dd31; здесь исправлено).

Тот же паттерн/переменные, что придумал broadcast.py для сводок (см. его
mirror_token()) — держи оба места в синхроне при правке имён/дефолтов.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

CHANNEL_MIRRORS = [c.strip() for c in
                    os.environ.get("NPZ_CHANNEL_MIRRORS", "@npz_karta_online").split(",")
                    if c.strip()]
MIRROR_TOKEN_PATH = os.environ.get("NPZ_MIRROR_TOKEN", "/root/.npz-site-bot/token")


def mirror_token():
    """Токен анонимного бота для зеркал. None — файла нет, зеркала пропускаем:
    лучше не запостить в зеркало, чем запостить его личным ботом."""
    try:
        return open(MIRROR_TOKEN_PATH).read().strip()
    except Exception as e:
        print("зеркала: нет токена %s (%s) — пропускаю" % (MIRROR_TOKEN_PATH, e))
        return None


def mirror_enabled(env_var, default="1"):
    """env_var=1 (или не задан, дефолт default) — зеркалирование включено."""
    return os.environ.get(env_var, default) == "1"


def _telegram_call(token, method, **params):
    """Вынесено отдельной функцией (а не инлайн в send_to_mirrors), чтобы тесты
    могли подменить именно вызов Telegram API, не трогая остальную логику."""
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (token, method), data=data)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error_code": e.code}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def send_to_mirrors(text, parse_mode="HTML", label="mirror"):
    """Шлёт text во все CHANNEL_MIRRORS анонимным ботом. Ошибка зеркала (нет
    токена, сбой Telegram) только логируется — падение зеркала НЕ должно
    ронять публикацию в основной канал (та к этому моменту уже случилась)."""
    token = mirror_token()
    if not token:
        return
    for chat_id in CHANNEL_MIRRORS:
        resp = _telegram_call(token, "sendMessage", chat_id=chat_id, text=text,
                               parse_mode=parse_mode, disable_web_page_preview="true")
        ok = resp.get("ok", False)
        print("%s: зеркало %s -> %s" % (label, chat_id, "ok" if ok else resp))
