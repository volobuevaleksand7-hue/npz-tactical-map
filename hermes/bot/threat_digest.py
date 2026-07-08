#!/usr/bin/env python3
"""
threat_digest.py — Дайджест угроз для cron (каждые 30 мин).
Считывает radar-state.json, формирует краткий отчёт по NPZ-регионам,
отправляет в Telegram подписчикам с активными alerts.
"""
import json, os, sys, datetime, urllib.request, urllib.parse

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA = os.path.join(REPO, "data")
TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
API = "https://api.telegram.org/bot" + TOKEN
SITE = "https://npz-tactical-map.vercel.app"

NPZ_REGIONS = [
    "Краснодарский край", "Ленинградская обл.", "Ярославская обл.",
    "Москва", "Московская обл.", "Республика Крым", "г. Севастополь",
    "Волгоградская обл.", "Самарская обл.", "Саратовская обл.", "Ростовская обл.",
]

REGION_OBJECTS = {
    "Краснодарский край": "Туапсинский НПЗ, Афипский НПЗ, Ильский НПЗ, Новороссийск",
    "Ленинградская обл.": "Кинеф (Кириши), Усть-Луга, Приморск",
    "Ярославская обл.": "НПЗ ЯНОС",
    "Москва": "Московский НПЗ (Капотня)",
    "Московская обл.": "Московский НПЗ (Капотня)",
    "Республика Крым": "Керченская ТЭЦ, Порт Кавказ",
    "г. Севастополь": "Порт Севастополь",
    "Волгоградская обл.": "Волгоградский НПЗ",
    "Самарская обл.": "Сызранский НПЗ, Куйбышевский НПЗ",
    "Саратовская обл.": "Саратовский НПЗ",
    "Ростовская обл.": "Новошахтинский НПЗ",
}

REGION_ALIASES = {
    "Москва и МО": "Москва", "Московская область": "Московская обл.",
    "Ленинградская область": "Ленинградская обл.", "Краснодар": "Краснодарский край",
    "Ростов": "Ростовская обл.", "Самара": "Самарская обл.",
    "Саратов": "Саратовская обл.", "Волгоград": "Волгоградская обл.",
    "Ярославль": "Ярославская обл.", "Крым": "Республика Крым",
    "Севастополь": "г. Севастополь",
}


def jload(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def match_region(name):
    if not name:
        return None
    n = name.strip()
    if n in NPZ_REGIONS:
        return n
    for alias, canonical in REGION_ALIASES.items():
        if alias in n or n in alias:
            return canonical
    for r in NPZ_REGIONS:
        if n in r or r in n:
            return r
    return None


def api_send(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    data = urllib.parse.urlencode(params).encode()
    try:
        r = urllib.request.urlopen(API + "/sendMessage", data=data, timeout=30)
        return json.loads(r.read().decode())
    except Exception as e:
        print(f"send err {chat_id}: {e}")
        return {}


def compute_digest():
    """Compute threat digest text from radar-state.json."""
    radar = jload(os.path.join(DATA, "radar-state.json"), {})
    cities_data = radar.get("cities", {})

    # threats per region
    threats = {}
    for region in NPZ_REGIONS:
        threats[region] = {"bpla": False, "rocket": False, "pvo": False, "cities": []}

    if isinstance(cities_data, dict):
        iterable = cities_data.values()
    else:
        iterable = cities_data or []

    for c in iterable:
        region = match_region(c.get("region", "")) or match_region(c.get("name", ""))
        if not region or region not in threats:
            continue
        if c.get("bpla"):
            threats[region]["bpla"] = True
        if c.get("rocket") or c.get("rk"):
            threats[region]["rocket"] = True
        if c.get("pvo"):
            threats[region]["pvo"] = True
        if c.get("bpla") or c.get("rocket") or c.get("rk"):
            threats[region]["cities"].append(c.get("name", ""))

    # timestamp
    ts = radar.get("timestamp") or radar.get("fetched_at", "")
    if isinstance(ts, (int, float)):
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        time_str = (dt + datetime.timedelta(hours=3)).strftime("%H:%M")
    else:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        time_str = (now_utc + datetime.timedelta(hours=3)).strftime("%H:%M")

    # build message
    active_regions = []
    clear_regions = []
    for region in NPZ_REGIONS:
        th = threats[region]
        has = th["bpla"] or th["rocket"]
        if has:
            active_regions.append((region, th))
        else:
            clear_regions.append(region)

    lines = [f"📡 <b>Дайджест угроз</b> · ⏰ {time_str} МСК", ""]

    if active_regions:
        lines.append("🔴 <b>Активные угрозы:</b>")
        for region, th in active_regions:
            parts = []
            if th["bpla"]:
                parts.append("БПЛА")
            if th["rocket"]:
                parts.append("ракеты")
            badges = " · ".join(parts)
            city_list = ", ".join(th["cities"][:4])
            if len(th["cities"]) > 4:
                city_list += f" +{len(th['cities']) - 4}"
            lines.append(f"  🔴 <b>{region}</b> ({badges})")
            if city_list:
                lines.append(f"     📍 {city_list}")
        lines.append("")
        lines.append(f"📊 Активных регионов: {len(active_regions)} из {len(NPZ_REGIONS)}")
    else:
        lines.append("✅ <b>Все NPZ-регионы чисты</b> — угроз не обнаружено.")

    lines.append("")
    lines.append(f'🔗 <a href="{SITE}/radar.html">Радар-карта</a>')
    return "\n".join(lines)


def main():
    text = compute_digest()
    print(text)
    print()

    # send to subscribers with active alerts
    subs_doc = jload(SUBS_PATH, {"subscribers": {}})
    subscribers = subs_doc.get("subscribers", {})
    sent = 0
    for cid, info in subscribers.items():
        if info.get("status") != "active":
            continue
        alerts = info.get("alerts") or {}
        if not alerts.get("enabled"):
            continue
        resp = api_send(cid, text)
        if resp.get("ok"):
            sent += 1
        print(f"  → {cid} ({info.get('name', '?')}): {'ok' if resp.get('ok') else 'fail'}")

    print(f"\nОтправлено: {sent}")


if __name__ == "__main__":
    main()
