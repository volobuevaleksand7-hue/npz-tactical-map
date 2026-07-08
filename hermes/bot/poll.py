#!/usr/bin/env python3
# poll.py — собрать новых подписчиков бота @NpzFuel_Bot через Telegram getUpdates
# (long-poll без вебхука; подходит для ручного/локального пайплайна карты).
# Обрабатывает /start (подписка), /stop (отписка), /status. Хранит подписчиков и
# offset в ~/.npz-bot/ (вне репозитория). Запускать перед broadcast и/или по крону.
import json, os, sys, time, urllib.request, urllib.parse, importlib.util, datetime

HOME = os.path.expanduser("~")

# подгружаем broadcast.py как модуль (для мгновенного дайджеста новому подписчику)
try:
    _spec = importlib.util.spec_from_file_location("npzbroadcast", os.path.join(os.path.dirname(__file__), "broadcast.py"))
    _bc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_bc)
except Exception:
    _bc = None
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
_TOKEN_PATH = os.path.join(BOT_DIR, "token")
TOKEN = open(_TOKEN_PATH).read().strip() if os.path.exists(_TOKEN_PATH) else ""  # import-safe (тест)
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "poll-state.json")
API = "https://api.telegram.org/bot" + TOKEN
SITE = "https://npz-tactical-map.vercel.app"
# Чат владельца для уведомлений о новых подписках (пусто = не слать; задаётся для @BPLAlert_bot)
OWNER_CHAT = os.environ.get("NPZ_OWNER_CHAT", "").strip()
# Отчёт о счётчике подписчиков через ДРУГОГО бота (напр. @NpzFuel_Bot → основной чат владельца).
# NPZ_REPORT_CHAT — куда слать, NPZ_REPORT_TOKEN — путь к токену бота-отправителя.
REPORT_CHAT = os.environ.get("NPZ_REPORT_CHAT", "").strip()
REPORT_TOKEN_FILE = os.environ.get("NPZ_REPORT_TOKEN", "").strip()


def _should_report(count):
    """Пороги отчёта по числу подписчиков: ≤25 каждый, ≤100 каждый 5-й,
    ≤500 каждый 10-й, дальше каждый 50-й."""
    if count <= 25:
        return True
    if count <= 100:
        return count % 5 == 0
    if count <= 500:
        return count % 10 == 0
    return count % 50 == 0


def _report_send(text):
    """Отправить отчёт через бота-отправителя (REPORT_TOKEN_FILE) в REPORT_CHAT."""
    if not (REPORT_CHAT and REPORT_TOKEN_FILE and os.path.exists(REPORT_TOKEN_FILE)):
        return
    try:
        tok = open(REPORT_TOKEN_FILE).read().strip()
        data = urllib.parse.urlencode({
            "chat_id": REPORT_CHAT, "text": text, "disable_web_page_preview": "true",
        }).encode()
        urllib.request.urlopen(
            "https://api.telegram.org/bot%s/sendMessage" % tok, data=data, timeout=20)
    except Exception as e:
        print("report send err", e)

WELCOME = ("✅ Вы подписаны на сводку «Топливный фронт РФ».\n\n"
           "После каждого обновления карты пришлю кратко: новые удары по НПЗ, ситуацию "
           "на АЗС и голоса людей — со ссылкой на карту.\n\n"
           "Открыть карту: " + SITE + "\n\n"
           "БПЛА-оповещения: /alerts\nОтписаться: /stop")
BYE = "Вы отписались. Вернуться — /start."

# ─── Inline-кнопки таймера угроз ───
TIMER_OPTIONS = [
    (10, "10м"), (30, "30м"), (60, "1ч"), (120, "2ч"),
    (360, "6ч"), (720, "12ч"), (1440, "24ч"),
]

def _timer_keyboard(current_interval=60):
    """Inline-кнопки выбора интервала угроз (по 4 в ряд, чтобы влезало на мобиле)."""
    buttons = []
    for minutes, label in TIMER_OPTIONS:
        prefix = "✅ " if minutes == current_interval else ""
        buttons.append({"text": f"{prefix}{label}", "callback_data": f"timer|{minutes}"})
    changes_active = current_interval == 0
    prefix = "✅ " if changes_active else ""
    buttons.append({"text": f"{prefix}🔔 По изменениям", "callback_data": "timer|changes"})
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    return {"inline_keyboard": rows}

def _interval_text(interval_min):
    """Человекочитаемый интервал."""
    if interval_min == 0:
        return "только при изменениях"
    if interval_min < 60:
        return f"каждые {interval_min} мин"
    hours = interval_min // 60
    return f"каждые {hours} ч" if hours > 1 else "каждый час"

# ─── /radar command ───
REPO = os.environ.get("NPZ_REPO", os.path.expanduser("~/npz-tactical-map"))
RADAR_CACHE = os.path.join(REPO, "data", "radar-cache.json")
RADAR_STATE = os.path.join(REPO, "data", "radar-state.json")
RADAR_URL = "https://radar-map.ru/api/state"
RADAR_TTL = 600  # 10 minutes

NPZ_REGIONS = {
    "Краснодарский край", "Ленинградская обл.", "Ярославская обл.",
    "Москва", "Московская обл.", "Республика Крым", "г. Севастополь",
    "Волгоградская обл.", "Самарская обл.", "Саратовская обл.", "Ростовская обл.",
}

REGION_OBJECTS = {
    "Краснодарский край": "Туапсинский НПЗ, Афипский НПЗ, Ильский НПЗ, Новороссийск, Тамань",
    "Ленинградская обл.": "Кинеф (Кириши), Усть-Луга, Приморск",
    "Ярославская обл.": "НПЗ ЯНОС",
    "Москва": "Московский НПЗ (Капотня)",
    "Московская обл.": "Московский НПЗ (Капотня)",
    "Республика Крым": "Керченская ТЭЦ, Порт Кавказ",
    "г. Севастополь": "Порт Севастополь",
    "Волгоградская обл.": "Волгоградский НПЗ",
    "Самарская обл.": "Сызранский НПЗ, Куйбышевский НПЗ, Новокуйбышевский НПЗ",
    "Саратовская обл.": "Саратовский НПЗ",
    "Ростовская обл.": "Новошахтинский НПЗ (НЗНП)",
}

REGION_ALIASES = {
    "Москва и МО": "Москва", "Московская область": "Московская обл.",
    "Ленинградская область": "Ленинградская обл.", "Краснодар": "Краснодарский край",
    "Ростов": "Ростовская обл.", "Самара": "Самарская обл.",
    "Саратов": "Саратовская обл.", "Волгоград": "Волгоградская обл.",
    "Ярославль": "Ярославская обл.", "Крым": "Республика Крым",
    "Севастополь": "г. Севастополь",
}

def _match_region(name):
    if not name: return None
    n = name.strip()
    if n in NPZ_REGIONS: return n
    for alias, canonical in REGION_ALIASES.items():
        if alias in n or n in alias: return canonical
    for r in NPZ_REGIONS:
        if n in r or r in n: return r
    return None

def _alert_helpers():
    sys.path.insert(0, os.path.dirname(__file__))
    from radar_alerts import NPZ_REGIONS as ALERT_REGIONS
    from radar_alerts import normalize_region, update_subscriber_alerts
    return ALERT_REGIONS, normalize_region, update_subscriber_alerts

def _alerts_help(info):
    alerts = info.get("alerts") or {}
    if not alerts.get("enabled"):
        return ("БПЛА-оповещения выключены.\n\n"
                "Включить: /alerts\nРегионы: /regions")
    regions = alerts.get("regions") or ["all"]
    region_text = "все NPZ-регионы" if "all" in regions else ", ".join(regions)
    interval = int(alerts.get("interval_min", 60))
    interval_text = "только изменения" if interval == 0 else "каждые %d мин при активной угрозе" % interval
    return ("📡 БПЛА-оповещения включены.\n\n"
            "Регион: %s\nЧастота: %s\n\n"
            "Поменять регион: /region Краснодар или /region all\n"
            "Поменять частоту: /interval 30, /interval 60 или /interval changes\n"
            "Выключить: /alerts_off") % (region_text, interval_text)

def _fetch_radar_cached():
    """Fetch radar data with 10-min cache. Returns (data, from_cache)."""
    now = time.time()
    cached = jload(RADAR_CACHE, {})
    if cached.get("ts") and now - cached["ts"] < RADAR_TTL and cached.get("data"):
        return cached["data"], True
    try:
        req = urllib.request.Request(RADAR_URL, headers={"User-Agent": "NPZ-Tactical-Map/1.0"})
        r = urllib.request.urlopen(req, timeout=15)
        data = json.loads(r.read().decode("utf-8"))
        json.dump({"ts": now, "data": data}, open(RADAR_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        return data, False
    except Exception as e:
        print("radar fetch error:", e)
        return cached.get("data"), True

def compute_radar_status():
    """Build /radar response text: active threats + recent changes."""
    data, from_cache = _fetch_radar_cached()
    if not data:
        return "📡 Радар: не удалось получить данные. Попробуйте позже."

    cities = data.get("cities", [])
    regions = data.get("regions", {})

    # Classify threats by NPZ region
    threats = {}  # region → { bpla: bool, rocket: bool, cities: [] }
    for c in cities:
        region = _match_region(c.get("region", "")) or _match_region(c.get("name", ""))
        if not region: continue
        if region not in threats:
            threats[region] = {"bpla": False, "rocket": False, "cities": []}
        if c.get("bpla"): threats[region]["bpla"] = True
        if c.get("rocket") or c.get("rk"): threats[region]["rocket"] = True
        if c.get("bpla") or c.get("rocket") or c.get("rk"):
            threats[region]["cities"].append(c.get("name", ""))

    # Region-level flags
    for src in ["lpr1_treugolnik", "vrv_radar"]:
        src_data = regions.get(src, {})
        for rname, active in src_data.items():
            if not active: continue
            region = _match_region(rname)
            if not region: continue
            if region not in threats:
                threats[region] = {"bpla": False, "rocket": False, "cities": []}
            threats[region]["bpla"] = True

    # Sources
    sources = []
    for src, label in [("lpr1_treugolnik", "ЛПР"), ("vrv_radar", "ВРВ")]:
        src_data = regions.get(src, {})
        if any(v for v in src_data.values() if v):
            sources.append(label)
    src_str = " · ".join(sources) if sources else ""

    # Recent changes from radar-state.json (last 30 min)
    prev_state = jload(RADAR_STATE, {"cities": {}, "timestamp": 0})
    recent_changes = []
    cutoff = time.time() - 1800  # 30 minutes
    if prev_state.get("timestamp", 0) > cutoff:
        prev_cities = prev_state.get("cities", {})
        for key, state in prev_cities.items():
            if state.get("bpla") or state.get("rocket"):
                # Check if this was previously inactive (became active recently)
                recent_changes.append(state.get("name", key.split("|")[0]))

    # Build message
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    msk = now_utc + datetime.timedelta(hours=3)
    time_str = msk.strftime("%H:%M")

    lines = ["📡 <b>Радар угроз НПЗ</b>", f"⏰ {time_str} МСК · {src_str}", ""]

    active_count = 0
    for region in sorted(NPZ_REGIONS):
        th = threats.get(region)
        has = th and (th["bpla"] or th["rocket"])
        if has: active_count += 1
        icon = "🔴" if has else "🟢"
        badge = ""
        if th and th["bpla"]: badge += " БПЛА"
        if th and th["rocket"]: badge += " РК"
        if not has: badge = " чисто"
        lines.append(f"{icon} <b>{region}</b>{badge}")
        lines.append(f"   Объекты: {REGION_OBJECTS.get(region, '—')}")
        if has and th["cities"]:
            lines.append(f"   Города: {', '.join(th['cities'][:5])}")
        lines.append("")

    if active_count == 0:
        lines.insert(2, "✅ <b>Нет активных угроз</b> — все NPZ-регионы чисты.\n")

    if recent_changes:
        lines.append("📋 <b>Изменения за 30 мин:</b>")
        for c in recent_changes[:5]:
            lines.append(f"  • {c}")
        lines.append("")

    lines.append(f"🔗 <a href=\"{SITE}/radar.html\">Открыть карту радара</a>")
    if from_cache:
        lines.append("<i>Данные из кэша (<10 мин)</i>")

    return "\n".join(lines)

def jload(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def api(method, **params):
    data = urllib.parse.urlencode(params).encode()
    try:
        r = urllib.request.urlopen(API + "/" + method, data=data, timeout=40)
        return json.loads(r.read().decode())
    except Exception as e:
        print("api err", method, e); return {}

def now_utc():
    import datetime; return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

def main():
    subsdoc = jload(SUBS_PATH, {"subscribers": {}})
    subs = subsdoc.setdefault("subscribers", {})
    st = jload(STATE_PATH, {})
    offset = st.get("offset", 0)

    added = removed = 0
    resp = api("getUpdates", offset=offset, timeout=0,
               allowed_updates=json.dumps(["message", "callback_query"]))
    for u in resp.get("result", []):
        offset = u["update_id"] + 1

        # ── inline-кнопки ──
        cbq = u.get("callback_query")
        if cbq:
            data = cbq.get("data") or ""
            cb_chat = cbq.get("message") or {}
            cb_cid = str((cb_chat.get("chat") or {}).get("id") or "")

            # Таймер угроз: timer|10, timer|30, timer|60, etc.
            if data.startswith("timer|"):
                raw = data.split("|", 1)[1]
                info = subs.setdefault(cb_cid, {"status": "active", "since": now_utc(), "name": ""})
                _, _, update_alerts = _alert_helpers()
                if raw == "changes":
                    update_alerts(info, enabled=True, interval_min=0)
                    new_interval = 0
                else:
                    try:
                        new_interval = int(raw)
                    except ValueError:
                        new_interval = 60
                    update_alerts(info, enabled=True, interval_min=new_interval)
                # Ответ на callback (уведомление внизу экрана)
                api("answerCallbackQuery", callback_query_id=cbq["id"],
                    text=f"⏱ Интервал: {_interval_text(new_interval)}")
                # Обновить сообщение с новой клавиатурой
                interval_now = int(info.get("alerts", {}).get("interval_min", 60))
                kb = _timer_keyboard(interval_now)
                api("editMessageReplyMarkup",
                    chat_id=cb_cid,
                    message_id=cb_chat.get("message_id"),
                    reply_markup=json.dumps(kb))
                continue

            # Опубликовать/Отклонить (из radar_publish)
            try:
                sys.path.insert(0, os.path.dirname(__file__))
                from radar_publish import handle_callback
                handle_callback(cbq)
            except Exception as e:
                print("callback_query err", e)
            continue

        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        cid = str(chat.get("id") or "")
        text = (msg.get("text") or "").strip().lower()
        if not cid: continue
        if text.startswith("/start"):
            info = subs.get(cid, {})
            new = info.get("status") != "active"
            info.update({"status":"active", "since": info.get("since") or now_utc(),
                         "src": (text.split(None,1)[1] if " " in text else info.get("src","")),
                         "name": chat.get("first_name") or chat.get("username") or ""})
            subs[cid] = info
            if new: added += 1
            # отчёт о счётчике подписчиков через @NpzFuel_Bot (пороговый, с водяным знаком)
            if new and REPORT_CHAT:
                active_now = sum(1 for v in subs.values() if v.get("status") == "active")
                if active_now > st.get("last_report_count", 0) and _should_report(active_now):
                    st["last_report_count"] = active_now
                    r_un = chat.get("username")
                    r_who = chat.get("first_name") or r_un or cid
                    r_uns = f"@{r_un}" if r_un else "—"
                    r_msk = (datetime.datetime.now(datetime.timezone.utc)
                             + datetime.timedelta(hours=3)).strftime("%d.%m %H:%M МСК")
                    _report_send(f"📊 @BPLAlert_bot: {active_now} подписчик(ов)\n"
                                 f"Новый: {r_who} ({r_uns}) · ID {cid}\n{r_msk}")
            # уведомление владельцу о новой подписке (только если задан NPZ_OWNER_CHAT)
            if new and OWNER_CHAT:
                uname = chat.get("username")
                who = chat.get("first_name") or uname or cid
                uns = f"@{uname}" if uname else "—"
                msk = (datetime.datetime.now(datetime.timezone.utc)
                       + datetime.timedelta(hours=3)).strftime("%d.%m %H:%M МСК")
                api("sendMessage", chat_id=OWNER_CHAT,
                    text=(f"🆕 Новая подписка\n{who} ({uns})\nID: {cid}\n"
                          f"Источник: {info.get('src') or 'бот'}\n{msk}"),
                    disable_web_page_preview="true")
            api("sendMessage", chat_id=cid, text=WELCOME, disable_web_page_preview="true")
            # мгновенная стартовая сводка новому подписчику (свежие данные, без ожидания прогона)
            if new and _bc is not None:
                try:
                    txt, _ = _bc.compute_digest(force_latest=True)
                    _bc.send(cid, txt)
                except Exception as e:
                    print("welcome-digest err", e)
        elif text.startswith("/stop"):
            if subs.get(cid, {}).get("status") == "active":
                subs[cid]["status"] = "stopped"; removed += 1
            api("sendMessage", chat_id=cid, text=BYE)
        elif text.startswith("/status"):
            active = subs.get(cid, {}).get("status") == "active"
            api("sendMessage", chat_id=cid, text=("Подписка активна ✅" if active else "Вы не подписаны. /start"))
        elif text.startswith("/radar"):
            api("sendMessage", chat_id=cid, text=compute_radar_status())
        elif text.startswith("/alerts_off"):
            info = subs.setdefault(cid, {"status": "active", "since": now_utc(), "name": chat.get("first_name") or chat.get("username") or ""})
            _, _, update_alerts = _alert_helpers()
            update_alerts(info, enabled=False)
            api("sendMessage", chat_id=cid, text="БПЛА-оповещения выключены. Включить снова: /alerts")
        elif text.startswith("/alerts"):
            info = subs.setdefault(cid, {"status": "active", "since": now_utc(), "name": chat.get("first_name") or chat.get("username") or ""})
            _, _, update_alerts = _alert_helpers()
            update_alerts(info, enabled=True)
            interval = int(info.get("alerts", {}).get("interval_min", 60))
            kb = _timer_keyboard(interval)
            help_text = _alerts_help(info)
            api("sendMessage", chat_id=cid, text=help_text,
                reply_markup=json.dumps(kb))
        elif text.startswith("/regions"):
            regions, _, _ = _alert_helpers()
            api("sendMessage", chat_id=cid, text="Доступные регионы:\n• " + "\n• ".join(regions) + "\n\nВсе регионы: /region all")
        elif text.startswith("/region"):
            value = (msg.get("text") or "").strip().split(None, 1)
            if len(value) < 2:
                api("sendMessage", chat_id=cid, text="Укажите регион: /region Краснодар или /region all\nСписок: /regions")
                continue
            info = subs.setdefault(cid, {"status": "active", "since": now_utc(), "name": chat.get("first_name") or chat.get("username") or ""})
            _, normalize_region, update_alerts = _alert_helpers()
            region = normalize_region(value[1])
            if not region:
                api("sendMessage", chat_id=cid, text="Не понял регион. Проверьте список: /regions")
                continue
            update_alerts(info, enabled=True, regions=[region])
            api("sendMessage", chat_id=cid, text=_alerts_help(info))
        elif text.startswith("/interval"):
            info = subs.setdefault(cid, {"status": "active", "since": now_utc(), "name": chat.get("first_name") or chat.get("username") or ""})
            _, _, update_alerts = _alert_helpers()
            # Поддержка текстового ввода /interval 30 для обратной совместимости
            value = (msg.get("text") or "").strip().split(None, 1)
            if len(value) >= 2:
                raw = value[1].strip().lower()
                if raw in ("changes", "change", "изменения"):
                    interval = 0
                else:
                    try:
                        interval = int(raw)
                    except ValueError:
                        interval = None
                if interval is not None:
                    update_alerts(info, enabled=True, interval_min=interval)
            current_interval = int(info.get("alerts", {}).get("interval_min", 60))
            kb = _timer_keyboard(current_interval)
            api("sendMessage", chat_id=cid, text=_alerts_help(info),
                reply_markup=json.dumps(kb))

    json.dump(subsdoc, open(SUBS_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    st["offset"] = offset  # сохраняем и offset, и last_report_count
    json.dump(st, open(STATE_PATH,"w",encoding="utf-8"))
    active = sum(1 for v in subs.values() if v.get("status")=="active")
    print("poll: +%d новых, -%d отписок | активных подписчиков: %d" % (added, removed, active))

if __name__ == "__main__":
    main()
