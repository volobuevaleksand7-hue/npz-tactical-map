#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import time
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA = os.path.join(REPO, "data")
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "radar-alert-state.json")
SITE = "https://npz-tactical-map.vercel.app"

NPZ_REGIONS = [
    "Краснодарский край", "Ленинградская обл.", "Ярославская обл.",
    "Москва", "Московская обл.", "Республика Крым", "г. Севастополь",
    "Волгоградская обл.", "Самарская обл.", "Саратовская обл.", "Ростовская обл.",
]

REGION_ALIASES = {
    "all": "all", "все": "all", "всё": "all",
    "Москва и МО": "Москва", "Московская область": "Московская обл.",
    "Ленинградская область": "Ленинградская обл.", "Краснодар": "Краснодарский край",
    "Ростов": "Ростовская обл.", "Самара": "Самарская обл.",
    "Саратов": "Саратовская обл.", "Волгоград": "Волгоградская обл.",
    "Ярославль": "Ярославская обл.", "Крым": "Республика Крым",
    "Севастополь": "г. Севастополь",
}


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


def normalize_region(name):
    name = str(name or "").strip()
    if not name:
        return None
    if name in REGION_ALIASES:
        return REGION_ALIASES[name]
    if name in NPZ_REGIONS:
        return name
    lower = name.lower()
    for alias, canonical in REGION_ALIASES.items():
        if alias.lower() in lower or lower in alias.lower():
            return canonical
    for region in NPZ_REGIONS:
        if lower in region.lower() or region.lower() in lower:
            return region
    return None


def update_subscriber_alerts(info, enabled=None, regions=None, interval_min=None):
    alerts = info.setdefault("alerts", {})
    if enabled is not None:
        alerts["enabled"] = bool(enabled)
    if regions is not None:
        normalized = []
        for region in regions:
            canonical = normalize_region(region)
            if canonical and canonical not in normalized:
                normalized.append(canonical)
        alerts["regions"] = normalized or ["all"]
    if interval_min is not None:
        alerts["interval_min"] = int(interval_min)
    alerts.setdefault("enabled", True)
    alerts.setdefault("regions", ["all"])
    alerts.setdefault("interval_min", 60)
    return alerts


def compute_threats(radar):
    threats = {region: {"active": False, "bpla": False, "rocket": False, "cities": []} for region in NPZ_REGIONS}
    cities = radar.get("cities", {})
    if isinstance(cities, dict):
        iterable = cities.values()
    else:
        iterable = cities or []
    for city in iterable:
        region = normalize_region(city.get("region", "")) or normalize_region(city.get("name", ""))
        if region not in threats:
            continue
        bpla = bool(city.get("bpla"))
        rocket = bool(city.get("rocket") or city.get("rk"))
        if bpla or rocket:
            threats[region]["active"] = True
            threats[region]["bpla"] = threats[region]["bpla"] or bpla
            threats[region]["rocket"] = threats[region]["rocket"] or rocket
            if city.get("name"):
                threats[region]["cities"].append(city["name"])
    return threats


def selected_regions(alerts):
    regions = alerts.get("regions") or ["all"]
    if "all" in regions:
        return NPZ_REGIONS[:]
    return [r for r in regions if r in NPZ_REGIONS]


def threat_label(threat):
    parts = []
    if threat.get("bpla"):
        parts.append("БПЛА")
    if threat.get("rocket"):
        parts.append("ракеты")
    return " / ".join(parts) if parts else "опасность"


def format_notice(region, threat, status):
    msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    time_str = msk.strftime("%H:%M")
    cities = ", ".join(threat.get("cities", [])[:5])
    if status == "new":
        head = "🔴 %s: опасность %s" % (region, threat_label(threat))
    elif status == "reminder":
        head = "🔴 %s: напоминание, опасность сохраняется" % region
    else:
        head = "🟢 %s: отбой опасности" % region
    lines = ["<b>%s</b>" % head, "⏰ %s МСК" % time_str]
    if cities and status != "clear":
        lines.append("Города/точки: %s." % cities)
    lines.append('Радар: <a href="%s/radar.html">открыть карту</a>.' % SITE)
    return "\n".join(lines)


def build_notifications(subscribers, radar, prev_state, now_ts=None):
    now_ts = int(now_ts or time.time())
    threats = compute_threats(radar)
    next_state = json.loads(json.dumps(prev_state or {}, ensure_ascii=False))
    notices = []
    for chat_id, info in subscribers.items():
        if info.get("status") != "active":
            continue
        alerts = info.get("alerts") or {}
        if not alerts.get("enabled"):
            continue
        interval_min = int(alerts.get("interval_min", 60))
        chat_state = next_state.setdefault(str(chat_id), {}).setdefault("regions", {})
        for region in selected_regions(alerts):
            threat = threats.get(region, {"active": False, "cities": []})
            prev = chat_state.get(region, {})
            was_active = bool(prev.get("active"))
            is_active = bool(threat.get("active"))
            last_sent = int(prev.get("last_sent_ts") or 0)
            status = None
            if is_active and not was_active:
                status = "new"
            elif is_active and interval_min and now_ts - last_sent >= interval_min * 60:
                status = "reminder"
            elif was_active and not is_active:
                status = "clear"
            if status:
                notices.append({
                    "chat_id": str(chat_id),
                    "region": region,
                    "status": status,
                    "cities": threat.get("cities", []),
                    "text": format_notice(region, threat, status),
                })
                last_sent = now_ts
            chat_state[region] = {"active": is_active, "last_sent_ts": last_sent}
    return notices, next_state


def send_message(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def format_group_text(notices):
    """Собирает все new/reminder-нотисы одного chat_id в единое сообщение."""
    msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    time_str = msk.strftime("%H:%M")
    lines = ["<b>🔴 Радар: угроза БПЛА / ракет</b>", "⏰ %s МСК" % time_str, "",
             "⚠️ <b>Активные регионы:</b>"]
    for n in notices:
        emoji = "🆕" if n["status"] == "new" else "🔴"
        region = n["region"]
        cities = n.get("cities", [])
        city_str = " (%s)" % ", ".join(cities[:5]) if cities else ""
        lines.append("%s <b>%s</b>%s" % (emoji, region, city_str))
    lines.append("")
    lines.append('📍 <a href="%s/radar.html">открыть карту радара</a>' % SITE)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Subscriber radar/BPLA alerts.")
    parser.add_argument("--send", action="store_true", help="Actually send Telegram alerts")
    parser.add_argument("--dry-run", action="store_true", help="Print alerts without sending")
    args = parser.parse_args()

    subs = jload(SUBS_PATH, {"subscribers": {}}).get("subscribers", {})
    radar = jload(os.path.join(DATA, "radar-state.json"), {})
    state = jload(STATE_PATH, {})
    notices, next_state = build_notifications(subs, radar, state)
    print("radar-alerts: %d raw notifications" % len(notices))

    # Группируем по chat_id: статусы new/reminder в одно сообщение,
    # clear — пока отдельно (их обычно 0-1 за раз)
    grouped = {}
    clears = []
    for notice in notices:
        if notice["status"] == "clear":
            clears.append(notice)
        else:
            chat_id = notice["chat_id"]
            grouped.setdefault(chat_id, []).append(notice)

    print("radar-alerts: %d grouped broadcasts, %d clears" % (len(grouped), len(clears)))

    if args.send:
        token = open(os.path.join(BOT_DIR, "token")).read().strip()
        sent = 0
        # Шлём групповые (одно сообщение на chat_id)
        for chat_id, group in grouped.items():
            text = format_group_text(group)
            resp = send_message(token, chat_id, text)
            if resp.get("ok"):
                sent += 1
        # Clear-нотисы шлём по-отдельности (их редко)
        for notice in clears:
            resp = send_message(token, notice["chat_id"], notice["text"])
            if resp.get("ok"):
                sent += 1
        jsave(STATE_PATH, next_state)
        print("radar-alerts: sent %d/%d messages" % (sent, len(grouped) + len(clears)))
    else:
        for notice in notices:
            print("[%s] %s -> %s" % (notice["status"], notice["chat_id"], notice["region"]))
            print(notice["text"])
            print("---")
        print("radar-alerts: dry-run only; state not saved")


if __name__ == "__main__":
    main()
