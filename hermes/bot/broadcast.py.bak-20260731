#!/usr/bin/env python3
# broadcast.py — единый публикатор «Топливный фронт РФ» в Telegram (редполитика v2,
# docs/npz-posting-style-v2.md). Рендер текста — ТОЛЬКО через render.py; дедуп —
# ТОЛЬКО через day_state.py (published_keys). Устаревшие diff-дайджест и
# editorial-дайджест оставлены как функции для совместимости, но в проде НЕ
# вызываются из publish-путей — только под NPZ_LEGACY=1 (см. §5 директивы).
#
# Использование:
#   python3 broadcast.py --briefing morning|evening        # утренняя/вечерняя сводка
#   python3 broadcast.py --briefing morning --dry-run       # показать текст, не слать
#   python3 broadcast.py --briefing morning --test <chat>   # тест-отправка только этому chat
#   python3 broadcast.py --update "текст пополнения"        # добавить 🔄-строку в активную сводку
#   python3 broadcast.py --molniya-published <headline> <url> <key>  # зарегистрировать молнию в day-state
#
# Legacy (по умолчанию отключено; включить NPZ_LEGACY=1, если очень нужно):
#   NPZ_LEGACY=1 python3 broadcast.py --dry-run
#   NPZ_LEGACY=1 python3 broadcast.py --editorial-dry-run
import json, os, sys, time, urllib.request, urllib.parse, datetime, subprocess

HOME = os.path.expanduser("~")
BOT_DIR = os.environ.get("NPZ_BOT_DIR", os.path.join(HOME, ".npz-bot"))
REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA = os.path.join(REPO, "data")
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "state.json")               # legacy diff snapshot
EDITORIAL_STATE_PATH = os.path.join(BOT_DIR, "editorial-state.json")  # legacy
SITE = "https://npz-tactical-map.vercel.app"
CHANNEL = os.environ.get("NPZ_CHANNEL", "@NPZmap")  # публичный канал-лента; "" чтобы отключить
TOKEN = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import day_state as DS

MONTHS = ["", "января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]

def load(fn, default=None):
    try: return json.load(open(os.path.join(DATA, fn), encoding="utf-8"))
    except Exception: return default if default is not None else {}

def jload(p, d):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def esc(s):
    s = "" if s is None else str(s)
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def api_url(method):
    global TOKEN
    if TOKEN is None:
        TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
    return "https://api.telegram.org/bot%s/%s" % (TOKEN, method)

def rudate(iso):
    try:
        y,m,d = str(iso)[:10].split("-"); return "%d %s" % (int(d), MONTHS[int(m)])
    except Exception: return str(iso or "")

def skey(x): return "|".join([str(x.get(k,"")) for k in ("date","time","city","target")])
def vkey(x): return "|".join([str(x.get("date","")), str(x.get("city","")), str(x.get("quote",""))[:40]])

def is_ru(q):
    """True, если цитата преимущественно на кириллице. Английский в рассылку не пускаем."""
    q = str(q or "")
    cyr = sum('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in q)
    lat = sum('a' <= c.lower() <= 'z' for c in q)
    return cyr >= lat


# ════════════════════════════════════════════════════════════════════════
# TELEGRAM API PRIMITIVES
# ════════════════════════════════════════════════════════════════════════

def kb():
    return {"inline_keyboard": [[
        {"text":"🗺 Открыть карту", "url": SITE + "/"},
        {"text":"⛽ Карта АЗС", "url": SITE + "/karta-azs"},
    ]]}

def send(chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode":"HTML",
        "disable_web_page_preview":"true", "reply_markup": json.dumps(kb()),
    }).encode()
    try:
        r = urllib.request.urlopen(api_url("sendMessage"), data=data, timeout=30)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode())
        except Exception: body = {"error_code": e.code}
        return None, body

def send_photo(chat_id, photo_path, caption):
    """sendPhoto через multipart/form-data. caption=None → без подписи."""
    boundary = "----npzcard7f3b"
    fields = {"chat_id": str(chat_id), "parse_mode": "HTML",
              "reply_markup": json.dumps(kb())}
    if caption is not None:
        fields["caption"] = caption
    body = b""
    for k, v in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                 % (boundary, k, v)).encode("utf-8")
    with open(photo_path, "rb") as f:
        photo = f.read()
    body += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"card.png\"\r\n"
             "Content-Type: image/png\r\n\r\n" % boundary).encode("utf-8")
    body += photo + b"\r\n" + ("--%s--\r\n" % boundary).encode("utf-8")
    req = urllib.request.Request(api_url("sendPhoto"), data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: berr = json.loads(e.read().decode())
        except Exception: berr = {"error_code": e.code}
        return None, berr

def edit_caption(chat_id, message_id, caption):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "message_id": message_id, "caption": caption,
        "parse_mode": "HTML", "reply_markup": json.dumps(kb()),
    }).encode()
    try:
        r = urllib.request.urlopen(api_url("editMessageCaption"), data=data, timeout=30)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode())
        except Exception: body = {"error_code": e.code}
        return None, body

def edit_text(chat_id, message_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "message_id": message_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": "true",
        "reply_markup": json.dumps(kb()),
    }).encode()
    try:
        r = urllib.request.urlopen(api_url("editMessageText"), data=data, timeout=30)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: body = json.loads(e.read().decode())
        except Exception: body = {"error_code": e.code}
        return None, body


def latest_cover_path():
    """Обложка дня из репозитория (та же, что на сайте /news): assets/cover-<дата>.png.
    Берём по максимальной дате ударов; None, если файла нет."""
    try:
        strikes = (load("strikes.json") or {}).get("strikes", [])
        dates = sorted({str(s.get("date", ""))[:10] for s in strikes if s.get("date")}, reverse=True)
        for d in dates[:3]:  # свежая дата или пара ближайших — что реально есть
            p = os.path.join(REPO, "assets", "cover-%s.png" % d)
            if os.path.exists(p):
                return p
    except Exception:
        pass
    return None


def render_digest_card():
    """Картинка для поста — обложка дня (assets/cover-<дата>.png). Фолбэк — render_card."""
    cover = latest_cover_path()
    if cover:
        return cover
    img = os.path.join(BOT_DIR, "last-card.png")
    try:
        from render_card import render_card
        render_card(build_card_payload(), img)
        return img
    except Exception as e:
        print("card: рендер не удался (%s) — шлю текстом" % e)
        return None


def send_card_or_text(chat_id, img, text):
    """Фото+подпись (если влезает в лимит 1024), иначе фото без подписи + текст отдельно.
    img=None → чистый текст (фолбэк, если рендер карточки не удался).
    Возвращает (media_result, text_result) — оба могут быть None в зависимости от режима."""
    if not img:
        ok, err = send(chat_id, text)
        return None, (ok, err)
    if R.entity_len(text) <= R.CAPTION_HARD_MAX:
        ok, err = send_photo(chat_id, img, text)
        return (ok, err), None
    media_ok, media_err = send_photo(chat_id, img, None)
    text_ok, text_err = (None, None)
    if media_ok:
        text_ok, text_err = send(chat_id, text)
    return (media_ok, media_err), (text_ok, text_err)


def _is_blocked_error(code, err):
    """403 (Forbidden) — юзер точно заблокировал бота, всегда blocked.
    400 (Bad Request) обычно означает ФОРМАТНУЮ ошибку запроса (битый chat_id,
    неверный HTML и т.п.), а НЕ блокировку — блокировать живого подписчика за это
    нельзя. Только 400 с описанием, явно говорящим про блокировку бота, считаем
    blocked; прочие 400 — просто логируемая ошибка отправки."""
    if code == 403:
        return True
    if code == 400:
        desc = str((err or {}).get("description", "")).lower()
        return "bot was blocked" in desc or "user is deactivated" in desc
    return False


def _deliver_simple(chat_ids, img, text, label="broadcast"):
    """Общая логика доставки: photo+caption или текст, всем в chat_ids. Возвращает (sent, failed)."""
    sent = failed = 0
    subsdoc = jload(SUBS_PATH, {"subscribers": {}})
    for c in chat_ids:
        media_res, text_res = send_card_or_text(c, img, text)
        ok = (media_res and media_res[0]) or (text_res and text_res[0]) or (not img and text_res and text_res[0])
        err = (media_res and media_res[1]) or (text_res and text_res[1])
        if ok:
            sent += 1
        else:
            failed += 1
            code = (err or {}).get("error_code")
            if _is_blocked_error(code, err):
                if c in subsdoc["subscribers"]:
                    subsdoc["subscribers"][c]["status"] = "blocked"
            elif code == 400:
                print("%s: ошибка 400 у %s (не блокировка): %s" % (label, c, (err or {}).get("description")))
            elif code == 429:
                time.sleep(int((err.get("parameters") or {}).get("retry_after", 2)))
        time.sleep(0.05)
    json.dump(subsdoc, open(SUBS_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return sent, failed


# ════════════════════════════════════════════════════════════════════════
# ДАННЫЕ ДЛЯ render_briefing()
# ════════════════════════════════════════════════════════════════════════

def _gather_briefing_data(molniya_ref=None, update_lines=None, date_iso=None):
    strikes = (load("strikes.json") or {}).get("strikes", [])
    voices = (load("fuel-voices.json") or {}).get("voices", [])
    azsdoc = load("fuel-availability.json") or {}
    fuel = load("fuel-state.json") or {}
    grid = load("grid-state.json") or {}
    date_iso = date_iso or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return {
        "strikes": strikes,
        "voices": voices,
        "azs": azsdoc.get("regions", []),
        "exchange": azsdoc.get("exchange", {}),
        "fuel": fuel,
        "grid": grid,
        "date_iso": date_iso,
        "molniya_ref": molniya_ref,
        "update_lines": update_lines or [],
        "site_page": "%s/news/%s" % (SITE, date_iso),
    }


def regenerate_site_page():
    """Запускает agents/gen-news.py, чтобы страница дня (/news/<дата>.html) была
    синхронизирована с публикуемой сводкой. Не фейлит публикацию, если упало."""
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(REPO, "agents", "gen-news.py")],
            cwd=REPO, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print("gen-news.py: код %d, stderr: %s" % (result.returncode, (result.stderr or "")[:300]))
            return False
        return True
    except Exception as e:
        print("gen-news.py: исключение %s" % e)
        return False


# ════════════════════════════════════════════════════════════════════════
# --briefing morning|evening (НОВЫЙ единый путь)
# ════════════════════════════════════════════════════════════════════════

def render_briefing_card(mode="morning"):
    """Картинка-сводка. Приоритет — обложка дня (та же, что на сайте), затем
    render_briefing.py генеративный рендер, финальный фолбэк — render_card."""
    cover = latest_cover_path()
    if cover:
        return cover
    img = os.path.join(BOT_DIR, "briefing-%s.png" % mode)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "render_briefing", os.path.join(os.path.dirname(__file__), "render_briefing.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.render_briefing(mode, img)
        return img
    except Exception as e:
        print("briefing card: рендер не удался (%s) — фолбэк на render_card" % e)
        return render_digest_card()


def do_briefing(mode, dry=False, test_chat=None):
    date_iso = DS.today_iso()
    state = DS.ensure_today(DS.load_state(), date_iso)

    # Утренняя/вечерняя — НОВАЯ сводка (не апдейт), сбрасываем update_lines для нового поста,
    # но сохраняем molniya_refs дня для лида, если молния уже была.
    molniya_ref = None
    if state.get("molniya_refs"):
        top = state["molniya_refs"][0]
        molniya_ref = {"headline": top.get("headline"), "url": top.get("url"),
                        "summary": "См. молнию для деталей."}

    data = _gather_briefing_data(molniya_ref=molniya_ref, update_lines=None, date_iso=date_iso)
    rendered = R.render_briefing(data, kind=mode)

    caption_or_text = rendered["caption_or_text"]
    text_mode = rendered["mode"]

    limit = R.CAPTION_HARD_MAX if text_mode == "caption" else R.TEXT_HARD_MAX
    ok_pf, reason_pf = R.preflight(caption_or_text, limit)
    if not ok_pf:
        print("briefing %s: preflight FAILED (%s) — отправка остановлена" % (mode, reason_pf))
        if not dry:
            return

    if dry:
        print("--- BRIEFING %s (dry-run, mode=%s) ---\n%s\n---" % (mode.upper(), text_mode, caption_or_text))
        if rendered.get("text"):
            print("--- (split) TEXT MESSAGE ---\n%s\n---" % rendered["text"])
        return

    img = render_briefing_card(mode)

    if test_chat:
        media_res, text_res = send_card_or_text(test_chat, img, caption_or_text)
        ok = bool((media_res and media_res[0]) or (text_res and text_res[0]))
        print("test briefing ->", test_chat, "ok" if ok else "ERR")
        return

    media_message_id = None
    text_message_id = None

    # Канал
    if CHANNEL:
        media_res, text_res = send_card_or_text(CHANNEL, img, caption_or_text)
        ok = bool((media_res and media_res[0]) or (text_res and text_res[0]))
        print("briefing %s: канал %s -> %s" % (mode, CHANNEL, "ok" if ok else "ERR"))
        if media_res and media_res[0]:
            media_message_id = (media_res[0].get("result") or {}).get("message_id")
        if text_res and text_res[0]:
            text_message_id = (text_res[0].get("result") or {}).get("message_id")

    # Личка
    subs = jload(SUBS_PATH, {}).get("subscribers", {})
    chats = [c for c, info in subs.items() if info.get("status", "active") == "active"]
    if chats:
        sent, failed = _deliver_simple(chats, img, caption_or_text, "briefing")
        print("briefing %s: отправлено %d, ошибок %d" % (mode, sent, failed))
    else:
        print("briefing %s: 0 активных подписчиков." % mode)

    # Записываем state model + регенерируем страницу дня.
    DS.set_publish_result(state, text_mode, media_message_id=media_message_id,
                           text_message_id=text_message_id, site_page=data["site_page"])
    state["update_lines"] = []  # новая сводка = новый день пополнений
    DS.save_state(state)

    is_final = (mode == "evening")
    regenerated = regenerate_site_page()
    print("briefing %s: страница дня %s (final=%s)" % (
        mode, "обновлена" if regenerated else "НЕ обновлена (см. лог выше)", is_final))


# ════════════════════════════════════════════════════════════════════════
# --update "текст пополнения" (editMessageCaption / editMessageText по mode)
# ════════════════════════════════════════════════════════════════════════

def do_update(update_text, molniya_url=None, dry=False):
    date_iso = DS.today_iso()
    state = DS.ensure_today(DS.load_state(), date_iso)

    if not state.get("media_message_id") and not state.get("text_message_id"):
        print("update: нет активной сводки на сегодня — сначала --briefing morning/evening.")
        return

    kind = "molniya" if molniya_url else "update"
    line = R.render_update_line(
        {"time_msk": R.now_msk().strftime("%H:%M"), "text": update_text, "molniya_url": molniya_url},
        kind=kind)

    # Симулируем итоговую сводку с добавленной строкой, чтобы проверить лимиты ДО применения.
    trial_state = dict(state)
    trial_lines = ([line] + state.get("update_lines", []))[:DS.MAX_UPDATE_LINES]
    data = _gather_briefing_data(update_lines=trial_lines, date_iso=date_iso)
    rendered = R.render_briefing(data, kind="morning" if state.get("mode") else "morning")

    mode = state.get("mode") or "caption"
    limit = R.CAPTION_HARD_MAX if mode == "caption" else R.TEXT_HARD_MAX
    new_len = R.entity_len(rendered["caption_or_text"] if mode == "caption" else (rendered["text"] or rendered["caption_or_text"]))

    switch_to_split = False
    if mode == "caption" and new_len > R.CAPTION_HARD_MAX:
        # Однократное переключение в split-mode: фото остаётся, текст уходит отдельным сообщением.
        switch_to_split = True
        mode = "split"

    if dry:
        print("--- UPDATE (dry-run) --- mode=%s switch_to_split=%s" % (mode, switch_to_split))
        print(line)
        return

    DS.add_update_line(state, line)

    final_text = rendered["caption_or_text"] if not switch_to_split else (rendered["text"] or rendered["caption_or_text"])
    ok_pf, reason_pf = R.preflight(final_text, R.CAPTION_HARD_MAX if mode == "caption" else R.TEXT_HARD_MAX)
    if not ok_pf:
        print("update: preflight FAILED (%s) — не применяю." % reason_pf)
        return

    if mode == "caption" and state.get("media_message_id"):
        ok, err = edit_caption(CHANNEL, state["media_message_id"], final_text)
        print("update: editMessageCaption ->", "ok" if (ok and ok.get("ok")) else ("ERR " + str(err)))
    elif mode == "split" and not switch_to_split and state.get("text_message_id"):
        ok, err = edit_text(CHANNEL, state["text_message_id"], final_text)
        print("update: editMessageText ->", "ok" if (ok and ok.get("ok")) else ("ERR " + str(err)))
    elif switch_to_split:
        # Однократный переход caption -> split: шлём НОВОЕ текстовое сообщение со ссылкой,
        # caption медиа-поста оставляем как есть (уже отправлен), а последующие апдейты
        # пойдут через editMessageText нового сообщения.
        ok, err = send(CHANNEL, final_text)
        if ok and ok.get("ok"):
            state["text_message_id"] = (ok.get("result") or {}).get("message_id")
            state["mode"] = "split"
            print("update: переключение в split-mode, новое текстовое сообщение отправлено.")
        else:
            print("update: ERR при переключении в split -", err)
    else:
        print("update: нет message_id для режима %s — пропускаю отправку, но строка сохранена в state." % mode)

    DS.save_state(state)
    regenerate_site_page()


# ════════════════════════════════════════════════════════════════════════
# МОЛНИЯ: регистрация ключа в day-state (вызывается из strike_pipeline/radar_publish)
# ════════════════════════════════════════════════════════════════════════

def register_molniya(headline, url, key):
    """Регистрирует опубликованную молнию в day-state: добавляет в published_keys
    (единый дедуп) и в molniya_refs (чтобы сводка на неё сослалась, не дублируя)."""
    state = DS.ensure_today(DS.load_state())
    DS.mark_published(state, key)
    DS.add_molniya_ref(state, headline, url, key)
    DS.save_state(state)
    return state


# ════════════════════════════════════════════════════════════════════════
# LEGACY (compute_digest / editorial) — НЕ вызываются из publish-путей.
# Оставлены для совместимости за NPZ_LEGACY=1.
# ════════════════════════════════════════════════════════════════════════

def build_snapshot():
    strikes = (load("strikes.json") or {}).get("strikes", [])
    voices  = (load("fuel-voices.json") or {}).get("voices", [])
    azs     = (load("fuel-availability.json") or {}).get("regions", [])
    return {
        "strike_keys": [skey(x) for x in strikes],
        "voice_keys":  [vkey(x) for x in voices],
        "azs_levels":  {r.get("region"): r.get("level") for r in azs if r.get("region")},
    }

def compute_digest(force_latest=False):
    """LEGACY. Возвращает (text_html, has_new). Не используется в проде (NPZ_LEGACY=1)."""
    strikes = (load("strikes.json") or {}).get("strikes", [])
    voices  = [v for v in (load("fuel-voices.json") or {}).get("voices", []) if is_ru(v.get("quote"))]
    azsdoc  = load("fuel-availability.json") or {}
    azs     = azsdoc.get("regions", [])
    exch    = azsdoc.get("exchange", {})
    prev    = jload(STATE_PATH, {})

    if force_latest or not prev:
        new_strikes = strikes[:4]
        new_voices  = voices[:3]
        azs_changes = []
    else:
        pk = set(prev.get("strike_keys", []))
        new_strikes = [x for x in strikes if skey(x) not in pk][:6]
        pv = set(prev.get("voice_keys", []))
        new_voices = [x for x in voices if vkey(x) not in pv][:3]
        plevel = prev.get("azs_levels", {})
        azs_changes = []
        for r in azs:
            reg = r.get("region"); lv = r.get("level")
            if reg and plevel.get(reg) != lv:
                azs_changes.append((reg, plevel.get(reg), lv))

    has_new = bool(new_strikes or new_voices or azs_changes)
    today = rudate(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"))
    L = ["<b>🔥 Топливный фронт РФ — сводка за %s</b>" % today, ""]
    if new_strikes:
        L.append("<b>💥 Удары</b>")
        for s in new_strikes:
            tgt = str(s.get("target","")).split("(")[0].split("—")[0].strip()[:60]
            conf = {"confirmed":"✓","reported":"·","rumored":"?"}.get(s.get("confidence"),"")
            L.append("• %s — %s %s" % (esc(s.get("city","")), esc(tgt), conf))
        L.append("")
    LV = {"calm":"спокойно","strained":"перебои","limited":"лимиты","severe":"талоны/QR","critical":"сухо"}
    if azs_changes:
        L.append("<b>⛽ АЗС</b>")
        for reg, old, new in azs_changes[:5]:
            L.append("• %s: %s" % (esc(reg), esc(LV.get(new, new or ""))))
        L.append("")
    if exch.get("ai95_spb_rub_t"):
        tr = {"spike":"скачок","rising":"рост","falling":"спад","stable":"стабильно"}.get(exch.get("trend"),"")
        L.append("💱 Биржа СПбМТСБ: АИ-95 %s ₽/т %s" % (esc(exch.get("ai95_spb_rub_t")), tr))
        L.append("")
    if new_voices:
        L.append("<b>🗣 Люди говорят</b>")
        for v in new_voices:
            q = str(v.get("quote","")).strip()
            if len(q) > 140: q = q[:137] + "…"
            L.append("• %s: «%s»" % (esc(v.get("city","")), esc(q)))
        L.append("")
    L.append('Источник: открытые данные карты.')
    return "\n".join(L).strip(), has_new

DEFICIT = {"strained", "limited", "severe", "critical"}

def build_card_payload():
    strikes = (load("strikes.json") or {}).get("strikes", [])
    voices  = [v for v in (load("fuel-voices.json") or {}).get("voices", []) if is_ru(v.get("quote"))]
    azsdoc  = load("fuel-availability.json") or {}
    azs     = azsdoc.get("regions", [])
    exch    = azsdoc.get("exchange", {})
    today_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def spaced(v):
        s = str(v)
        return "{:,}".format(int(s)).replace(",", " ") if s.isdigit() else s

    stats = []
    if exch.get("ai95_spb_rub_t"):
        stats.append({"label": "Биржа АИ-95", "value": "%s ₽/т" % spaced(exch.get("ai95_spb_rub_t"))})
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    recent = sum(1 for s in strikes if str(s.get("date", ""))[:10] >= cutoff)
    if recent:
        stats.append({"label": "Ударов за неделю", "value": str(recent)})
    ndef = sum(1 for r in azs if r.get("level") in DEFICIT)
    if azs:
        stats.append({"label": "Регионов с дефицитом", "value": str(ndef)})

    quote = None
    if voices:
        v0 = voices[0]
        quote = {"city": str(v0.get("city", "")), "text": str(v0.get("quote", "")).strip()}

    return {
        "date_str": rudate(today_iso),
        "headline": "Топливный фронт РФ",
        "stats": stats[:3],
        "quote": quote,
    }

def build_editorial(ignore_dedupe=False):
    from editorial_digest import build_editorial_post
    return build_editorial_post(DATA, state_path=EDITORIAL_STATE_PATH, ignore_dedupe=ignore_dedupe)

def render_editorial_card(post):
    img = os.path.join(BOT_DIR, "last-editorial-card.png")
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
        from render_card import render_card
        render_card(post.get("card_payload") or {}, img)
        return img
    except Exception as e:
        print("editorial card: рендер не удался (%s) — шлю текстом" % e)
        return None

def mark_editorial_published(post):
    from editorial_digest import mark_published
    mark_published(post, state_path=EDITORIAL_STATE_PATH)

def post_channel(chat_id, text):
    img = render_digest_card()
    media_res, text_res = send_card_or_text(chat_id, img, text)
    return (media_res or text_res)


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    legacy_enabled = os.environ.get("NPZ_LEGACY") == "1"
    editorial_dry = "--editorial-dry-run" in args
    editorial = legacy_enabled and (os.environ.get("NPZ_EDITORIAL") == "1" or editorial_dry)
    force = "--force" in args
    briefing_mode = None
    if "--briefing" in args:
        i = args.index("--briefing")
        briefing_mode = args[i + 1] if i + 1 < len(args) else "morning"
    test_chat = None
    if "--test" in args:
        i = args.index("--test"); test_chat = args[i+1] if i+1 < len(args) else None
    update_text = None
    if "--update" in args:
        i = args.index("--update")
        update_text = args[i + 1] if i + 1 < len(args) else None
    molniya_url = None
    if "--molniya-url" in args:
        i = args.index("--molniya-url")
        molniya_url = args[i + 1] if i + 1 < len(args) else None

    # === НОВЫЙ единый путь: сводка ===
    if briefing_mode:
        do_briefing(briefing_mode, dry=dry, test_chat=test_chat)
        return

    # === НОВЫЙ путь: пополнение сводки ===
    if update_text is not None:
        do_update(update_text, molniya_url=molniya_url, dry=dry)
        return

    # === Регистрация молнии в day-state (единый дедуп) ===
    if "--molniya-published" in args:
        i = args.index("--molniya-published")
        headline, url, key = args[i+1], args[i+2], args[i+3]
        register_molniya(headline, url, key)
        print("molniya registered: %s" % key)
        return

    # === LEGACY: редакционный дайджест — только под NPZ_LEGACY=1 ===
    if editorial:
        post = build_editorial(ignore_dedupe=bool(test_chat) or force or editorial_dry)
        text, has_new = post["text"], bool(post.get("should_publish"))
        if dry or editorial_dry:
            print("--- EDITORIAL DIGEST (dry-run, LEGACY) ---")
            print("kind=%s visual=%s should_publish=%s reason=%s" % (
                post.get("kind"), (post.get("visual") or {}).get("type"),
                post.get("should_publish"), post.get("reason")))
            print("dedupe_key=%s" % post.get("dedupe_key"))
            print(text)
            print("---")
            return
        if test_chat:
            img = render_editorial_card(post)
            res = send_card_or_text(test_chat, img, text)
            print("test editorial ->", test_chat, res)
            return
        print("editorial: NPZ_LEGACY=1 указан, но публикация в канал из legacy-пути ОТКЛЮЧЕНА по умолчанию политикой v2.")
        return

    # === LEGACY: обычный diff-дайджест — только под NPZ_LEGACY=1 ===
    if legacy_enabled:
        text, has_new = compute_digest(force_latest=bool(test_chat))
        if dry:
            print("--- DIGEST (dry-run, LEGACY) ---\n" + text + "\n--- has_new=%s ---" % has_new); return
        if test_chat:
            res = post_channel(test_chat, text)
            print("test send ->", test_chat, res)
            return
        print("legacy digest: NPZ_LEGACY=1 указан, но публикация в канал из legacy-пути ОТКЛЮЧЕНА по умолчанию политикой v2.")
        return

    print("broadcast.py: не указан режим. Используйте --briefing morning|evening, --update \"текст\", "
          "или NPZ_LEGACY=1 для устаревших путей (см. шапку файла).")

if __name__ == "__main__":
    main()
