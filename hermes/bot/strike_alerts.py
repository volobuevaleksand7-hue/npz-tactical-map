#!/usr/bin/env python3
"""
strike_alerts.py — рассылка ПОДТВЕРЖДЁННЫХ УДАРОВ (data/strikes.json) подписчикам
бота с флагом alerts.attacks. Отдельно от radar_alerts.py (тот шлёт УГРОЗЫ-радар).

Дедуп по strike["id"] в <BOT_DIR>/strike-alert-state.json.
Init-guard: при первом запуске (нет state) — засеять все текущие id и НЕ рассылать
архив задним числом.

Удары ОДНОГО прогона группируются по времени СОБЫТИЯ (date+time), не по времени
прогона: разрыв между соседними ударами ≤ GROUP_GAP_HOURS — одно сообщение
списком, > GROUP_GAP_HOURS — отдельное сообщение на группу.

Удары старше MAX_AGE_HOURS от текущего момента не рассылаются вообще (молния —
про «сейчас»), но помечаются seen — иначе просроченный бэклог блокирует дедуп
навсегда. Порог + группировка добавлены 09.08.2026 после инцидента: сбойный
прогон копил бэклог несколько часов (см. executions.db на hermes-vps), а когда
наконец прошёл — разослал 11 старых ударов (28.07–01.08) отдельными сообщениями.

Использование (как у radar_alerts.py):
  NPZ_BOT_DIR=/root/.npz-bot-bpl python3 strike_alerts.py --dry-run
  NPZ_BOT_DIR=/root/.npz-bot-bpl python3 strike_alerts.py --send
"""
import argparse
import datetime
import json
import os
import re
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

# Молния — про «сейчас»: событие старше этого возраста тихо уходит в seen, без рассылки.
MAX_AGE_HOURS = 36
# Удары одного прогона с разрывом между событиями ≤ этого порога — одно сообщение списком.
GROUP_GAP_HOURS = 2
# Больше этого числа непрочитанных ударов за прогон — состояние рассинхронизировано с
# архивом, а не «много новостей»: досеиваем без рассылки. Реальный максимум за сутки —
# единицы, так что 20 не заденет живой поток даже в очень активный день.
RESEED_THRESHOLD = 20

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


def strike_key(strike):
    """Стабильный ключ дедупа: id, а если его нет (старый архив/сбой) — date|time|city|target."""
    return strike.get("id") or "|".join(str(strike.get(k, "")) for k in ("date", "time", "city", "target"))


def strike_event_dt(strike):
    """Время СОБЫТИЯ удара в UTC (date+time из strikes.json), для свежести и группировки.
    time бывает текстовым ('ночь'/'утро'/пусто) — тогда берём полдень даты. Дату
    распарсить не удалось — берём текущий момент (не роняем удар в 'старьё' по ошибке)."""
    date_s = str(strike.get("date") or "")[:10]
    try:
        base = datetime.date.fromisoformat(date_s)
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)
    hh, mm = 12, 0
    m = re.match(r"^(\d{1,2}):(\d{2})", str(strike.get("time") or "").strip())
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
    return datetime.datetime(base.year, base.month, base.day, hh, mm, tzinfo=datetime.timezone.utc)


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
    is_rocket = strike.get("type") == "rocket"
    kind = "Ракетный удар" if is_rocket else "Удар БПЛА"
    weapon = "🚀" if is_rocket else "🛩"
    when = "%s, %s" % (rudate(strike.get("date")), msk_time(strike.get("time")))
    lines = ["<b>💥%s %s</b>" % (weapon, kind)]
    head = city
    if target_short:
        head = "%s — %s" % (city, target_short) if city else target_short
    if head:
        lines.append(head)
    lines.append("🕐 %s" % when)
    lines.append('📍 <a href="%s/radar.html">карта</a>' % SITE)
    return "\n".join(lines)


def _head(strike):
    """«Город — объект» одной строкой (объект обрезан до первого « — », как в format_strike)."""
    city = strike.get("city") or ""
    target = (strike.get("target") or "").split(" — ")[0].strip()
    if city and target:
        return "%s — %s" % (city, target)
    return city or target


def format_group(strikes):
    """Несколько ударов одного окна — ОДНИМ сообщением: общий заголовок, строка на удар,
    одна ссылка на карту. Повторять шапку и ссылку на каждый удар — это и есть спам."""
    kinds = {s.get("type") == "rocket" for s in strikes}
    weapon, kind = ("🚀", "Ракетные удары") if kinds == {True} else \
                   (("🛩", "Удары БПЛА") if kinds == {False} else ("", "Удары"))
    dates = {str(s.get("date"))[:10] for s in strikes}
    lines = ["<b>💥%s %s (%d)</b>" % (weapon, kind, len(strikes))]
    if len(dates) == 1:
        lines.append("🕐 %s" % rudate(strikes[0].get("date")))
        lines.append("")
        for s in strikes:
            lines.append("• %s · %s" % (msk_time(s.get("time")), _head(s)))
    else:
        lines.append("")
        for s in strikes:
            lines.append("• %s, %s · %s" % (rudate(s.get("date")), msk_time(s.get("time")), _head(s)))
    lines.append("")
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


def build_strike_notifications(strikes, subscribers, seen, max_age_hours=None, now=None):
    """(notices, new_seen). notices = [{chat_id, strike_id, text, event_dt}].
    seen — множество уже разосланных id. Новые id всегда добавляются в new_seen
    (даже если адресатов нет ИЛИ удар отсеян по свежести), чтобы не копить и не
    перебирать архив повторно.
    max_age_hours — если задан, удары СТАРШЕ этого возраста (по факту события,
    strike_event_dt) в notices не попадают — молния про 'сейчас', не задним числом."""
    seen = set(seen or [])
    new_seen = set(seen)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    notices = []
    for s in strikes:
        sid = strike_key(s)
        if sid in seen:
            continue
        new_seen.add(sid)
        event_dt = strike_event_dt(s)
        if max_age_hours is not None and (now - event_dt) > datetime.timedelta(hours=max_age_hours):
            continue
        canonical = strike_region(s)
        text = format_strike(s)
        for chat_id, info in subscribers.items():
            if info.get("status") != "active":
                continue
            if _wants(info.get("alerts") or {}, canonical):
                notices.append({"chat_id": str(chat_id), "strike_id": sid, "text": text,
                                "event_dt": event_dt, "strike": s})
    return notices, new_seen


def group_notices_for_send(notices, gap_hours=GROUP_GAP_HOURS):
    """Схлопывает адресные уведомления ОДНОГО подписчика в сообщения по времени
    СОБЫТИЯ: разрыв между соседними ударами (в порядке события) ≤ gap_hours —
    один текст списком, > gap_hours — отдельное сообщение на группу.
    Возвращает [{"chat_id", "text", "strike_ids": [...]}, ...]."""
    by_chat = {}
    for n in notices:
        by_chat.setdefault(n["chat_id"], []).append(n)
    out = []
    for chat_id, items in by_chat.items():
        items = sorted(items, key=lambda n: n["event_dt"])
        groups, cur, prev_dt = [], [], None
        for n in items:
            if cur and (n["event_dt"] - prev_dt) > datetime.timedelta(hours=gap_hours):
                groups.append(cur)
                cur = []
            cur.append(n)
            prev_dt = n["event_dt"]
        if cur:
            groups.append(cur)
        for g in groups:
            if len(g) == 1:
                text = g[0]["text"]
            else:
                text = format_group([n["strike"] for n in g])
            out.append({"chat_id": chat_id, "text": text, "strike_ids": [n["strike_id"] for n in g]})
    return out


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
        seed = [strike_key(s) for s in strikes]
        jsave(STATE_PATH, {"seen": seed})
        print("strike-alerts: init — засеяно %d id, рассылка архива пропущена" % len(seed))
        return

    seen = state.get("seen", [])

    # Re-seed guard. Init-guard выше срабатывает, только если файла состояния НЕТ.
    # 09.08.2026: у нового контура бота файл БЫЛ, но отставший (seen=9 при 365 ударах
    # в архиве) и с унаследованными 26 живыми подписчиками — прогон поставил в очередь
    # 4 224 сообщения, упёрся в таймаут 3600с и был убит ДО сохранения seen, поэтому
    # следующий прогон начинал ту же рассылку заново. Отставание такого масштаба — это
    # не «много новостей», это несинхронное состояние: досеиваем молча и говорим об
    # этом в логе, чтобы расхождение было видно.
    unseen = sum(1 for s in strikes if strike_key(s) not in set(seen))
    if unseen > RESEED_THRESHOLD:
        if args.dry_run:
            print("strike-alerts: re-seed СРАБОТАЛ БЫ — непрочитанных %d (> %d); "
                  "dry-run, состояние НЕ сохранено" % (unseen, RESEED_THRESHOLD))
        else:
            jsave(STATE_PATH, {"seen": sorted({strike_key(s) for s in strikes})})
            print("strike-alerts: re-seed — непрочитанных %d (> %d), состояние отстало от "
                  "архива; засеяно %d id, рассылка пропущена" % (unseen, RESEED_THRESHOLD, len(strikes)))
        return

    notices, new_seen = build_strike_notifications(strikes, subs, seen, max_age_hours=MAX_AGE_HOURS)
    grouped = group_notices_for_send(notices)
    print("strike-alerts: %d новых-адресных сообщений -> %d к отправке (сгруппировано)"
          % (len(notices), len(grouped)))

    if args.send:
        token = open(os.path.join(BOT_DIR, "token")).read().strip()
        sent = 0
        for g in grouped:
            try:
                resp = send_message(token, g["chat_id"], g["text"])
                if resp.get("ok"):
                    sent += 1
            except Exception as e:  # HTTPError(403 заблокировал)/сеть — не роняем прогон
                print("FAIL chat=%s strikes=%s: %s" % (g["chat_id"], ",".join(g["strike_ids"]), e))
        # Коммитим seen ВСЕГДА после попытки (иначе на след. прогоне — дубли всем)
        jsave(STATE_PATH, {"seen": sorted(new_seen)})
        print("strike-alerts: отправлено %d/%d" % (sent, len(grouped)))
    else:
        for g in grouped:
            print("-> %s (%d удар(ов): %s)" % (g["chat_id"], len(g["strike_ids"]), ",".join(g["strike_ids"])))
            print(g["text"])
            print("---")
        print("strike-alerts: dry-run, state НЕ сохранён")


if __name__ == "__main__":
    main()
