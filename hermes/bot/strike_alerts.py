#!/usr/bin/env python3
"""
strike_alerts.py — рассылка ПОДТВЕРЖДЁННЫХ УДАРОВ (data/strikes.json) подписчикам
бота с флагом alerts.attacks. Отдельно от radar_alerts.py (тот шлёт УГРОЗЫ-радар).

Дедуп по strike["id"] в <BOT_DIR>/strike-alert-state.json.
Init-guard: при первом запуске (нет state) — засеять все текущие id и НЕ рассылать
архив задним числом.

Использование (как у radar_alerts.py):
  NPZ_BOT_DIR=/root/.npz-bot-bpl python3 strike_alerts.py --dry-run
  NPZ_BOT_DIR=/root/.npz-bot-bpl python3 strike_alerts.py --send
"""
import argparse
import datetime
import json
import os
import sys

# Переиспользуем нормализацию регионов и отправку из radar_alerts (тот же каталог)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radar_alerts import NPZ_REGIONS, normalize_region, send_message  # noqa: E402

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA = os.path.join(REPO, "data")
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "strike-alert-state.json")
STRIKES_PATH = os.path.join(DATA, "strikes.json")
SITE = "https://npz-tactical-map.vercel.app"

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def jload(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jsave(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def rudate(iso):
    try:
        y, m, d = str(iso)[:10].split("-")
        return "%d %s" % (int(d), MONTHS[int(m)])
    except Exception:
        return str(iso or "")


def msk_time(t):
    """'13:34 UTC' -> '16:34 МСК'. Если распарсить нельзя — вернуть как есть."""
    try:
        hh, mm = str(t).strip().split()[0].split(":")[:2]
        h = (int(hh) + 3) % 24
        return "%02d:%02d МСК" % (h, int(mm))
    except Exception:
        return str(t or "")


def strike_region(strike):
    """Каноничный NPZ-регион удара или None.
    strikes.json даёт полную форму («Самарская область»), а NPZ_REGIONS — «Самарская обл.»;
    normalize_region (радарный, город→регион) её не мапит, поэтому сперва свод «область→обл.»."""
    raw = (strike.get("region") or "").strip()
    cand = raw.replace(" область", " обл.")
    if cand in NPZ_REGIONS:
        return cand
    return normalize_region(raw) or normalize_region(strike.get("city"))


def format_strike(strike):
    city = strike.get("city") or ""
    target = strike.get("target") or ""
    # target бывает длинным с описанием установок — берём до первого « — »
    target_short = target.split(" — ")[0].strip() if target else ""
    kind = "ракетный удар" if strike.get("type") == "rocket" else "удар БПЛА"
    when = "%s, %s" % (rudate(strike.get("date")), msk_time(strike.get("time")))
    lines = ["<b>💥 Зафиксирован %s</b>" % kind]
    head = city
    if target_short:
        head = "%s — %s" % (city, target_short) if city else target_short
    if head:
        lines.append(head)
    lines.append("🕐 %s" % when)
    lines.append('📍 <a href="%s/radar.html">карта</a>' % SITE)
    return "\n".join(lines)


def _wants(alerts, canonical):
    """Подходит ли удар в регионе canonical подписчику с настройками alerts."""
    if not alerts.get("enabled", True):
        return False
    if alerts.get("attacks", True) is False:
        return False
    regions = alerts.get("regions") or ["all"]
    if "all" in regions:
        return True
    if canonical and canonical in regions:
        return True
    return False


def build_strike_notifications(strikes, subscribers, seen):
    """(notices, new_seen). notices = [{chat_id, strike_id, text}].
    seen — множество уже разосланных id. Новые id всегда добавляются в new_seen
    (даже если адресатов нет), чтобы не копить и не перебирать архив повторно."""
    seen = set(seen or [])
    new_seen = set(seen)
    notices = []
    for s in strikes:
        sid = s.get("id")
        if not sid or sid in seen:
            continue
        new_seen.add(sid)
        canonical = strike_region(s)
        text = format_strike(s)
        for chat_id, info in subscribers.items():
            if info.get("status") != "active":
                continue
            if _wants(info.get("alerts") or {}, canonical):
                notices.append({"chat_id": str(chat_id), "strike_id": sid, "text": text})
    return notices, new_seen


def main():
    parser = argparse.ArgumentParser(description="Deliver confirmed strikes to subscribers.")
    parser.add_argument("--send", action="store_true", help="Actually send Telegram messages")
    parser.add_argument("--dry-run", action="store_true", help="Print without sending")
    args = parser.parse_args()

    strikes = jload(STRIKES_PATH, {}).get("strikes", [])
    subs = jload(SUBS_PATH, {"subscribers": {}}).get("subscribers", {})
    state = jload(STATE_PATH, None)

    # Init-guard: первого state нет → засеять все id, ничего не слать.
    if state is None:
        seed = [s.get("id") for s in strikes if s.get("id")]
        jsave(STATE_PATH, {"seen": seed})
        print("strike-alerts: init — засеяно %d id, рассылка архива пропущена" % len(seed))
        return

    seen = state.get("seen", [])
    notices, new_seen = build_strike_notifications(strikes, subs, seen)
    print("strike-alerts: %d новых-адресных сообщений" % len(notices))

    if args.send:
        token = open(os.path.join(BOT_DIR, "token")).read().strip()
        sent = 0
        for n in notices:
            try:
                resp = send_message(token, n["chat_id"], n["text"])
                if resp.get("ok"):
                    sent += 1
            except Exception as e:  # HTTPError(403 заблокировал)/сеть — не роняем прогон
                print("FAIL chat=%s strike=%s: %s" % (n["chat_id"], n["strike_id"], e))
        # Коммитим seen ВСЕГДА после попытки (иначе на след. прогоне — дубли всем)
        jsave(STATE_PATH, {"seen": sorted(new_seen)})
        print("strike-alerts: отправлено %d/%d" % (sent, len(notices)))
    else:
        for n in notices:
            print("-> %s (strike %s)" % (n["chat_id"], n["strike_id"]))
            print(n["text"])
            print("---")
        print("strike-alerts: dry-run, state НЕ сохранён")


if __name__ == "__main__":
    main()
