#!/usr/bin/env python3
# broadcast.py — дайджест «Топливный фронт РФ» в Telegram после обновления карты.
# Читает data/*.json, сравнивает с прошлым снапшотом (state.json), шлёт подписчикам
# ТОЛЬКО новое (новые удары / изменения АЗС / свежие голоса). Токен и подписчики —
# в ~/.npz-bot/ (вне репозитория). Никаких секретов в коде.
#
# Использование:
#   python3 broadcast.py                 # обычный прогон: diff → рассылка всем, сохранить снапшот
#   python3 broadcast.py --dry-run       # показать дайджест, НЕ слать, НЕ менять снапшот
#   python3 broadcast.py --test <chat>   # собрать дайджест из СВЕЖИХ данных и послать ТОЛЬКО этому chat (превью)
#   python3 broadcast.py --force         # слать даже если diff пуст (текущая сводка)
import json, os, sys, time, urllib.request, urllib.parse, datetime

HOME = os.path.expanduser("~")
BOT_DIR = os.path.join(HOME, ".npz-bot")
REPO = os.environ.get("NPZ_REPO", os.path.join(HOME, "Documents", "npz-tactical-map"))
DATA = os.path.join(REPO, "data")
TOKEN = open(os.path.join(BOT_DIR, "token")).read().strip()
SUBS_PATH = os.path.join(BOT_DIR, "subscribers.json")
STATE_PATH = os.path.join(BOT_DIR, "state.json")
SITE = "https://npz-tactical-map.vercel.app"
CHANNEL = os.environ.get("NPZ_CHANNEL", "@NPZmap")  # публичный канал-лента; "" чтобы отключить
API = "https://api.telegram.org/bot" + TOKEN

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
    """Возвращает (text_html, has_new). force_latest=True → из свежих данных без diff (для превью)."""
    strikes = (load("strikes.json") or {}).get("strikes", [])
    voices  = [v for v in (load("fuel-voices.json") or {}).get("voices", []) if is_ru(v.get("quote"))]
    azsdoc  = load("fuel-availability.json") or {}
    azs     = azsdoc.get("regions", [])
    exch    = azsdoc.get("exchange", {})
    prev    = jload(STATE_PATH, {})

    if force_latest or not prev:
        new_strikes = strikes[:4]
        new_voices  = voices[:3]
        azs_changes = []  # для превью не считаем изменения
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

    # АЗС: сводка (изменения если есть, иначе краткий статус биржи)
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
    """Структура для картинки-карточки (render_card). Берёт ТЕКУЩИЕ данные, не diff."""
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
    # удары за последние 7 дней
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

def kb():
    return {"inline_keyboard": [[
        {"text":"🗺 Открыть карту", "url": SITE + "/"},
        {"text":"⛽ Карта АЗС", "url": SITE + "/?view=azs"},
    ]]}

def send(chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode":"HTML",
        "disable_web_page_preview":"true", "reply_markup": json.dumps(kb()),
    }).encode()
    try:
        r = urllib.request.urlopen(API + "/sendMessage", data=data, timeout=30)
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
    req = urllib.request.Request(API + "/sendPhoto", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: berr = json.loads(e.read().decode())
        except Exception: berr = {"error_code": e.code}
        return None, berr

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
    """Картинка для поста. ПРИОРИТЕТ — обложка дня с сайта (assets/cover-<дата>.png),
    чтобы в Telegram и на сайте было ОДНО фото. Фолбэк — авто-рендер карточки render_card."""
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
    img=None → чистый текст (фолбэк, если рендер карточки не удался)."""
    if not img:
        return send(chat_id, text)
    if len(text) <= 1024:
        return send_photo(chat_id, img, text)
    ok, err = send_photo(chat_id, img, None)
    if ok:
        send(chat_id, text)
    return ok, err

def post_channel(chat_id, text):
    """Пост в канал: карточка-картинка + текст. Фолбэк на чистый текст, если картинка не собралась."""
    img = render_digest_card()
    return send_card_or_text(chat_id, img, text)

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    force = "--force" in args
    test_chat = None
    if "--test" in args:
        i = args.index("--test"); test_chat = args[i+1] if i+1 < len(args) else None

    text, has_new = compute_digest(force_latest=bool(test_chat))

    if dry:
        print("--- DIGEST (dry-run) ---\n" + text + "\n--- has_new=%s ---" % has_new); return

    if test_chat:
        ok, err = post_channel(test_chat, text)
        print("test send ->", test_chat, "ok" if ok else ("ERR "+str(err)))
        return

    if not has_new and not force:
        print("broadcast: нет нового с прошлой рассылки — ничего не шлю (снапшот обновлю).")
        json.dump(build_snapshot(), open(STATE_PATH,"w",encoding="utf-8"), ensure_ascii=False)
        return

    # Карточка-картинка рендерится ОДИН раз и переиспользуется и в канале, и в личках.
    img = render_digest_card()

    # 1) Публичный канал-лента — один пост (карточка + текст) на всех подписчиков канала.
    if CHANNEL:
        ok, err = send_card_or_text(CHANNEL, img, text)
        print("broadcast: канал %s -> %s" % (CHANNEL, "ok" if ok else ("ERR "+str(err))))

    # 2) Личка — персональная рассылка тем, кто нажал /start у бота (тоже с карточкой).
    subs = jload(SUBS_PATH, {}).get("subscribers", {})
    chats = [c for c,info in subs.items() if info.get("status","active")=="active"]
    if not chats:
        print("broadcast: 0 активных подписчиков в личке."); json.dump(build_snapshot(), open(STATE_PATH,"w",encoding="utf-8"), ensure_ascii=False); return

    sent = failed = 0
    subsdoc = jload(SUBS_PATH, {"subscribers":{}})
    for c in chats:
        ok, err = send_card_or_text(c, img, text)
        if ok: sent += 1
        else:
            failed += 1
            code = (err or {}).get("error_code")
            if code in (403, 400):  # blocked / deactivated → пометить
                subsdoc["subscribers"].get(c, {})["status"] = "blocked"
            elif code == 429:
                time.sleep(int((err.get("parameters") or {}).get("retry_after", 2)))
                ok2, _ = send_card_or_text(c, img, text)
                if ok2: sent += 1; failed -= 1
        time.sleep(0.05)  # ~20/сек
    json.dump(subsdoc, open(SUBS_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(build_snapshot(), open(STATE_PATH,"w",encoding="utf-8"), ensure_ascii=False)
    print("broadcast: отправлено %d, ошибок %d, подписчиков %d" % (sent, failed, len(chats)))

if __name__ == "__main__":
    main()
