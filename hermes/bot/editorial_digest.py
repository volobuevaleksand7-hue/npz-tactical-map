#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
import re

SITE = "https://npz-tactical-map.vercel.app"
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
DEFICIT = {"strained", "limited", "severe", "critical"}
CONF_RU = {"confirmed": "подтверждено", "reported": "сообщается", "rumored": "требует подтверждения"}


def load_json(data_dir, name, default):
    try:
        with open(os.path.join(data_dir, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rudate(iso):
    try:
        y, m, d = str(iso)[:10].split("-")
        return "%d %s" % (int(d), MONTHS[int(m)])
    except Exception:
        return str(iso or "")


def parse_time(value):
    if isinstance(value, datetime.datetime):
        return value.astimezone(datetime.timezone.utc)
    text = str(value or "").replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(text)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)


def parse_date(value):
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def is_ru(text):
    text = str(text or "")
    cyr = sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in text)
    lat = sum("a" <= c.lower() <= "z" for c in text)
    return cyr >= lat and cyr > 0


def norm(text):
    text = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    return re.sub(r"[^0-9a-zа-яё ]+", "", text)


def short_target(strike):
    text = " ".join([str(strike.get("target", "")), str(strike.get("title", ""))]).lower()
    if "нпз" in text or "янос" in text or "нефтеперераб" in text:
        return "НПЗ"
    if "нефтебаз" in text or "топлив" in text or "терминал" in text:
        return "топливная инфраструктура"
    if "подстанц" in text or "тэц" in text or "электр" in text:
        return "энергообъект"
    target = str(strike.get("target") or strike.get("title") or "инфраструктура")
    return target.split("(")[0].split("—")[0].strip()[:42] or "инфраструктура"


def spaced(value):
    try:
        return "{:,}".format(int(value)).replace(",", " ")
    except Exception:
        return str(value or "")


def pick_lead(strikes, now_dt):
    today = now_dt.date()
    best = None
    for strike in strikes:
        d = parse_date(strike.get("date"))
        age = (today - d).days if d else 999
        text = norm(" ".join([
            str(strike.get("target", "")),
            str(strike.get("title", "")),
            str(strike.get("detail", "")),
        ]))
        score = 0
        if age <= 1:
            score += 120
        elif age <= 3:
            score += 70
        else:
            score -= min(age, 30)
        if any(k in text for k in ("нпз", "янос", "нефтеперераб", "нефтебаз", "топлив", "терминал")):
            score += 55
        if any(k in text for k in ("подстанц", "тэц", "электр", "блэкаут")):
            score += 30
        score += {"confirmed": 30, "reported": 15, "rumored": -15}.get(strike.get("confidence"), 0)
        if best is None or score > best[0]:
            best = (score, strike)
    if best and best[0] >= 85:
        return best[1]
    return None


def first_voice(voices):
    for voice in voices:
        quote = str(voice.get("quote", "")).strip()
        if is_ru(quote):
            return voice
    return None


def stats_context(azs, fuel, exchange):
    ndef = sum(1 for r in azs if r.get("level") in DEFICIT)
    severe = [r.get("region", "") for r in azs if r.get("level") in ("critical", "severe")]
    refineries = fuel.get("refineries", []) or []
    down = sum(1 for r in refineries if r.get("status") == "down")
    partial = sum(1 for r in refineries if r.get("status") == "partial")
    offline_pct = (fuel.get("national_balance", {}) or {}).get("capacity_offline_pct")
    return {
        "ndef": ndef,
        "severe": [x for x in severe if x][:4],
        "down": down,
        "partial": partial,
        "offline_pct": offline_pct,
        "exchange": exchange or {},
    }


def consequence_sentence(ctx):
    parts = []
    if ctx["offline_pct"]:
        parts.append("оценочно вне строя до %s%% перерабатывающих мощностей" % ctx["offline_pct"])
    if ctx["down"] or ctx["partial"]:
        parts.append("%d НПЗ остановлены, %d работают частично" % (ctx["down"], ctx["partial"]))
    if ctx["ndef"]:
        parts.append("дефицитные режимы отмечены в %d регионах" % ctx["ndef"])
    if not parts:
        return "это событие добавляет давление на топливную логистику и региональные запасы."
    return "; ".join(parts) + "."


def event_post(strike, ctx, voice, now_dt):
    city = str(strike.get("city") or strike.get("region") or "РФ")
    target = short_target(strike)
    headline = "%s: %s" % (city, target)
    fact_target = str(strike.get("target") or strike.get("title") or target).split("(")[0].strip()
    confidence = CONF_RU.get(strike.get("confidence"), "по открытым данным")
    lines = [
        "<b>%s</b>" % esc(headline),
        "",
        "<b>Главное:</b> %s — %s." % (esc(city), esc(fact_target)),
        "<b>Почему важно:</b> %s" % esc(consequence_sentence(ctx)),
        "<b>Статус:</b> %s; обновление проверено по открытым источникам карты." % esc(confidence),
    ]
    if voice:
        quote = str(voice.get("quote", "")).strip()
        if len(quote) > 130:
            quote = quote[:127].rstrip() + "..."
        lines.extend(["", "<b>С места:</b> %s: «%s»" % (esc(voice.get("city", "")), esc(quote))])
    lines.extend(["", 'Карта: <a href="%s/">открыть слой НПЗ и АЗС</a>.' % SITE])
    stats = []
    if ctx["offline_pct"]:
        stats.append({"label": "Мощности вне строя", "value": "%s%%" % ctx["offline_pct"]})
    if ctx["down"] or ctx["partial"]:
        stats.append({"label": "Проблемных НПЗ", "value": str(ctx["down"] + ctx["partial"])})
    if ctx["ndef"]:
        stats.append({"label": "Регионов с дефицитом", "value": str(ctx["ndef"])})
    if not stats:
        stats.append({"label": "Событие", "value": "новое"})
    return {
        "kind": "event",
        "headline": headline,
        "text": "\n".join(lines).strip(),
        "visual": {"type": "event_card"},
        "card_payload": {
            "date_str": rudate(now_dt.date().isoformat()),
            "headline": headline,
            "stats": stats[:3],
            "quote": None,
        },
        "dedupe_key": "event|%s|%s|%s|%s" % (
            strike.get("date", ""), norm(city), norm(fact_target or target), strike.get("confidence", "")),
    }


def monitoring_post(ctx, voice, now_dt):
    exchange = ctx["exchange"]
    lines = ["<b>Топливный фронт: мониторинг</b>", ""]
    if exchange.get("ai95_spb_rub_t"):
        trend = {"spike": "резкий скачок", "rising": "рост", "falling": "снижение", "stable": "стабильно"}.get(exchange.get("trend"), "")
        lines.append("<b>Биржа:</b> АИ-95 %s ₽/т%s." % (esc(spaced(exchange.get("ai95_spb_rub_t"))), (" — " + trend) if trend else ""))
    if ctx["ndef"]:
        regions = ", ".join(ctx["severe"][:3]) if ctx["severe"] else "без тяжёлых регионов в топе"
        lines.append("<b>АЗС:</b> дефицитные режимы в %d регионах; тяжёлые точки: %s." % (ctx["ndef"], esc(regions)))
    else:
        lines.append("<b>АЗС:</b> массового дефицита в текущих данных нет.")
    if ctx["down"] or ctx["partial"] or ctx["offline_pct"]:
        lines.append("<b>НПЗ:</b> %s" % esc(consequence_sentence(ctx)))
    if voice:
        quote = str(voice.get("quote", "")).strip()
        if len(quote) > 125:
            quote = quote[:122].rstrip() + "..."
        lines.append("<b>Сигнал:</b> %s: «%s»." % (esc(voice.get("city", "")), esc(quote)))
    lines.extend(["", 'Карта: <a href="%s/">смотреть регионы и АЗС</a>.' % SITE])
    stats = []
    if exchange.get("ai95_spb_rub_t"):
        stats.append({"label": "Биржа АИ-95", "value": "%s ₽/т" % spaced(exchange.get("ai95_spb_rub_t"))})
    stats.append({"label": "Регионов с дефицитом", "value": str(ctx["ndef"])})
    if ctx["down"] or ctx["partial"]:
        stats.append({"label": "Проблемных НПЗ", "value": str(ctx["down"] + ctx["partial"])})
    fingerprint = "|".join([
        str(exchange.get("ai95_spb_rub_t", "")),
        str(ctx["ndef"]),
        str(ctx["down"]),
        str(ctx["partial"]),
        hashlib.sha1(str((voice or {}).get("quote", "")).encode("utf-8")).hexdigest()[:8],
    ])
    return {
        "kind": "monitoring",
        "headline": "Топливный фронт: мониторинг",
        "text": "\n".join(lines).strip(),
        "visual": {"type": "monitoring_card"},
        "card_payload": {
            "date_str": rudate(now_dt.date().isoformat()),
            "headline": "Топливный фронт РФ",
            "stats": stats[:3],
            "quote": None,
        },
        "dedupe_key": "monitoring|%s|%s" % (now_dt.date().isoformat(), fingerprint),
    }


def is_duplicate(key, state_path, now_dt):
    if not state_path:
        return False
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    for item in state.get("published", []):
        if item.get("key") != key:
            continue
        published_at = parse_time(item.get("published_at"))
        if (now_dt - published_at).total_seconds() < 36 * 3600:
            return True
    return False


def mark_published(post, state_path, now=None):
    if not state_path or not post or not post.get("dedupe_key"):
        return
    now_dt = parse_time(now)
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    items = [x for x in state.get("published", []) if x.get("key") != post["dedupe_key"]]
    items.insert(0, {"key": post["dedupe_key"], "published_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
    state["published"] = items[:100]
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def build_editorial_post(data_dir, state_path=None, now=None, ignore_dedupe=False):
    now_dt = parse_time(now)
    strikes = (load_json(data_dir, "strikes.json", {}) or {}).get("strikes", []) or []
    voices = (load_json(data_dir, "fuel-voices.json", {}) or {}).get("voices", []) or []
    azsdoc = load_json(data_dir, "fuel-availability.json", {}) or {}
    fuel = load_json(data_dir, "fuel-state.json", {}) or {}
    ctx = stats_context(azsdoc.get("regions", []) or [], fuel, azsdoc.get("exchange", {}) or {})
    voice = first_voice(voices)
    lead = pick_lead(strikes, now_dt)
    post = event_post(lead, ctx, voice, now_dt) if lead else monitoring_post(ctx, voice, now_dt)
    duplicate = (not ignore_dedupe) and is_duplicate(post["dedupe_key"], state_path, now_dt)
    post["should_publish"] = not duplicate
    post["reason"] = "duplicate" if duplicate else "ready"
    return post
