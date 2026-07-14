#!/usr/bin/env python3
# render.py — единый рендер-модуль «Топливный фронт РФ» по редполитике v2
# (docs/npz-posting-style-v2.md). Все публикаторы (briefing/molniya/uav-alert/
# update-line) обязаны рендерить текст ЗДЕСЬ, а не собирать HTML вручную —
# так эмодзи-грамматика, лимиты длины, allowlist тегов и preflight остаются
# едиными для канала, личек и сайта.
#
# Публичный API:
#   render_briefing(data, kind="morning"|"evening") -> {"mode": "caption"|"split",
#       "caption_or_text": str, "text": str|None, "headline": str}
#   render_molniya(event) -> str
#   render_uav_alert(regions, since_msk, source, cleared=False) -> str
#   render_update_line(update, kind="update"|"molniya") -> str
#   preflight(html_text, limit) -> (ok: bool, reason: str|None)
#
# Самотест: python3 -m hermes.bot.render --selftest
import datetime
import html
import re
import sys

SITE = "https://npz-tactical-map.vercel.app"
MSK = datetime.timezone(datetime.timedelta(hours=3))

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

DEFICIT_LEVELS = {"strained", "limited", "severe", "critical"}
LEVEL_RU = {"calm": "спокойно", "strained": "перебои", "limited": "лимиты",
            "severe": "талоны/QR", "critical": "сухо"}

CAPTION_HARD_MAX = 1024
CAPTION_TARGET = 900
TEXT_HARD_MAX = 4096
TEXT_TARGET = 3800
MOLNIYA_MAX = 500
UAV_ALERT_MAX = 200

# Allowlist Telegram HTML tags (parse_mode=HTML).
ALLOWED_TAGS = {"b", "i", "u", "s", "code", "a", "blockquote", "tg-spoiler"}
_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>")
_ENTITY_STRIP_RE = re.compile(r"<[^>]+>")
_BARE_URL_RE = re.compile(r"(?<!href=\")(?<!\">)(https?://[^\s<]+)")


def esc(s):
    """HTML-экранирование данных из источников: &, <, > (Telegram parse_mode=HTML)."""
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_attr(s):
    """Экранирование для href-атрибута (& и кавычки)."""
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace('"', "&quot;")


def rudate(iso):
    try:
        y, m, d = str(iso)[:10].split("-")
        return "%d %s" % (int(d), MONTHS[int(m)])
    except Exception:
        return str(iso or "")


def spaced(v):
    try:
        return "{:,}".format(int(v)).replace(",", " ")
    except Exception:
        return str(v or "")


def now_msk():
    return datetime.datetime.now(datetime.timezone.utc).astimezone(MSK)


def entity_len(text_html):
    """Entity-aware длина: длина текста ПОСЛЕ снятия HTML-тегов (то, что реально
    видит пользователь и что считает Telegram при проверке лимита caption/text)."""
    stripped = _ENTITY_STRIP_RE.sub("", text_html or "")
    return len(html.unescape(stripped))


def preflight(text_html, limit):
    """Preflight перед отправкой: allowlist тегов, нет голых URL, нет пустых блоков,
    длина в пределах limit (entity-aware). Возвращает (ok, reason)."""
    text_html = text_html or ""

    for m in _TAG_RE.finditer(text_html):
        tag = m.group(1).lower()
        if tag not in ALLOWED_TAGS:
            return False, "недопустимый тег <%s>" % tag

    # Голые URL — ищем http(s):// НЕ внутри href="..."
    without_hrefs = re.sub(r'href="[^"]*"', 'href=""', text_html)
    if _BARE_URL_RE.search(without_hrefs):
        return False, "голый URL вне <a href>"

    if re.search(r"<b>\s*</b>|<i>\s*</i>|<blockquote[^>]*>\s*</blockquote>", text_html):
        return False, "пустой блок"

    length = entity_len(text_html)
    if length > limit:
        return False, "превышен лимит длины: %d > %d" % (length, limit)

    return True, None


def _truncate_to(text_html, limit, suffix="…"):
    """Грубое сокращение по entity-aware длине (для аварийного случая >4096)."""
    if entity_len(text_html) <= limit:
        return text_html
    # Режем по обычным строкам снизу вверх, сохраняя структуру тегов насколько можно.
    lines = text_html.split("\n")
    while lines and entity_len("\n".join(lines)) > limit - len(suffix):
        lines.pop()
    return "\n".join(lines).rstrip() + "\n" + suffix


# ──────────────────────────────────────────────────────────────
# УТРЕННЯЯ / ВЕЧЕРНЯЯ СВОДКА
# ──────────────────────────────────────────────────────────────

def _is_ru(q):
    q = str(q or "")
    cyr = sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in q)
    lat = sum("a" <= c.lower() <= "z" for c in q)
    return cyr >= lat and cyr > 0


def _short_target(strike):
    text = str(strike.get("target") or strike.get("title") or "").split("(")[0].split("—")[0].strip()
    return text[:60] or "инфраструктура"


def _pick_lead(strikes, molniya_ref=None):
    """Выбрать «главное событие суток». Если была молния — она и есть главное
    (лид ссылается на неё), иначе — самый свежий/значимый удар."""
    if molniya_ref:
        return None  # лид формируется отдельно из molniya_ref
    if not strikes:
        return None
    # Простая эвристика: подтверждённые удары по НПЗ/энергетике вперёд, дальше по свежести.
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    def score(s):
        text = (str(s.get("target", "")) + str(s.get("title", ""))).lower()
        sc = 0
        if any(k in text for k in ("нпз", "нефтеперераб", "нефтебаз", "терминал")):
            sc += 50
        if any(k in text for k in ("тэц", "подстанц", "электр")):
            sc += 30
        sc += {"confirmed": 20, "reported": 10}.get(s.get("confidence"), 0)
        # Бонус за свежесть: удары сегодняшнего дня +100, вчерашнего +50
        sdate = str(s.get("date", ""))[:10]
        if sdate == today:
            sc += 100
        elif sdate >= (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime("%Y-%m-%d"):
            sc += 50
        return sc
    return max(strikes, key=score)


def _strike_repeat_count(strike, all_strikes):
    """Считает, какая по счёту атака на этот же объект (по нормализованному target)."""
    def norm(s):
        return re.sub(r"[^0-9a-zа-яё]+", "", str(s or "").lower())
    key = norm(strike.get("target") or strike.get("title"))
    if not key:
        return 1, []
    dates = sorted({str(s.get("date", ""))[:10] for s in all_strikes
                    if norm(s.get("target") or s.get("title")) == key and s.get("date")})
    return len(dates), dates


def render_briefing(data, kind="morning"):
    """Строит сводку по редполитике v2. data — dict с ключами:
       strikes (list), voices (list), azs (list), exchange (dict), fuel (dict),
       grid (dict), date_iso (str), molniya_ref ({"headline","url"} | None),
       update_lines (list[str], уже отрендеренные 🔄-строки, максимум 3).
       Возвращает {"mode": "caption"|"split", "caption_or_text": str, "text": str|None,
       "headline": str}."""
    strikes = data.get("strikes") or []
    voices = [v for v in (data.get("voices") or []) if _is_ru(v.get("quote"))]
    azs = data.get("azs") or []
    exch = data.get("exchange") or {}
    fuel = data.get("fuel") or {}
    grid = data.get("grid") or {}
    date_iso = data.get("date_iso") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    molniya_ref = data.get("molniya_ref")
    update_lines = (data.get("update_lines") or [])[:3]

    kind_label = "Утренняя" if kind == "morning" else "Вечерняя"
    time_label = "08:00 МСК" if kind == "morning" else "20:00 МСК"
    date_ru = rudate(date_iso)

    nb = fuel.get("national_balance", {}) or {}
    refineries = fuel.get("refineries", []) or []
    down = sum(1 for r in refineries if r.get("status") == "down")
    partial = sum(1 for r in refineries if r.get("status") == "partial")
    offline_pct = nb.get("capacity_offline_pct")

    cutoff_24h = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d")
    recent = [s for s in strikes if str(s.get("date", ""))[:10] >= cutoff_24h]
    npz_hits = sum(1 for s in recent if any(
        k in (str(s.get("target", "")) + str(s.get("title", ""))).lower()
        for k in ("нпз", "нефтеперераб", "тэц", "энерг", "подстанц")))

    lead_strike = None if molniya_ref else _pick_lead(recent or strikes)

    L = []

    # ── Заголовок-крючок ──
    if molniya_ref:
        headline = molniya_ref.get("headline", "Главное событие суток")
    elif lead_strike:
        headline = "%s: %s" % (lead_strike.get("city", "РФ"), _short_target(lead_strike))
    else:
        headline = "Топливный фронт РФ — %s сводка" % kind_label.lower()
    headline = headline[:90]

    L.append("🔴 <b>%s</b>" % esc(headline))
    L.append("<i>%s сводка · %s, %s · Топливный фронт РФ</i>" % (kind_label, date_ru, time_label))
    L.append("")

    # ── Апдейты дня (если пополнение) ──
    for ul in update_lines:
        L.append(ul)
    if update_lines:
        L.append("")

    # ── Лид ──
    if molniya_ref:
        L.append("Главное событие суток — МОЛНИЯ выше. %s" % esc(molniya_ref.get("summary", "")))
        if molniya_ref.get("url"):
            L.append('👉 <a href="%s">Подробности молнии</a>' % esc_attr(molniya_ref["url"]))
    elif lead_strike:
        conf = "✓ подтверждено" if lead_strike.get("confidence") == "confirmed" else "~ ожидает подтверждения"
        detail = str(lead_strike.get("detail") or lead_strike.get("title") or "").strip()
        if len(detail) > 220:
            cut = detail[:217].rsplit(" ", 1)[0]
            detail = cut.rstrip(",.;:") + "…"
        lead_line = "%s — %s." % (esc(lead_strike.get("city", "")), esc(_short_target(lead_strike)))
        if detail:
            lead_line += " %s" % esc(detail)
        L.append(lead_line)
        L.append("Статус: %s." % conf)
    else:
        L.append("Существенных изменений за отчётный период не зафиксировано.")
    L.append("")

    # ── Удары за сутки ──
    if recent:
        L.append("💥 <b>Удары за сутки: %d (%d — по НПЗ и энергетике)</b>" % (len(recent), npz_hits))
        shown = recent[:3]
        rest = recent[3:]
        for s in shown:
            conf = {"confirmed": "✓", "reported": "~"}.get(s.get("confidence"), "~")
            n, dates = _strike_repeat_count(s, strikes)
            repeat = " — %d-я атака" % n if n > 1 else ""
            L.append("📍 %s: %s%s %s" % (esc(s.get("city", "")), esc(_short_target(s)), esc(repeat), conf))
        if rest:
            detail_lines = []
            for s in rest:
                conf = {"confirmed": "✓", "reported": "~"}.get(s.get("confidence"), "~")
                detail_lines.append("%s: %s %s" % (esc(s.get("city", "")), esc(_short_target(s)), conf))
            L.append("<blockquote expandable>ещё %d ударов: %s</blockquote>" % (
                len(rest), "; ".join(detail_lines)))
        L.append("")

    # ── Переработка / АЗС / Биржа ──
    if down or partial or offline_pct:
        parts = []
        if down:
            parts.append("стоит %d НПЗ" % down)
        if partial:
            parts.append("частично %d" % partial)
        if offline_pct:
            parts.append("выбито ~%s%% мощностей" % offline_pct)
        L.append("🏭 <b>Переработка:</b> %s" % esc(" · ".join(parts)))

    ndef = sum(1 for r in azs if r.get("level") in DEFICIT_LEVELS)
    severe_regions = [r.get("region", "") for r in azs if r.get("level") in ("critical", "severe")]
    if severe_regions or ndef:
        line = "⛽ <b>АЗС:</b>"
        if severe_regions:
            line += " сухо — %s" % esc(", ".join(severe_regions[:4]))
        if ndef > len(severe_regions):
            line += "; лимиты/талоны — ещё %d регионов" % (ndef - len(severe_regions))
        L.append(line)

    if exch.get("ai95_spb_rub_t"):
        trend_ru = {"spike": "скачок", "rising": "рост", "falling": "спад",
                    "stable": "стабильно"}.get(exch.get("trend"), "")
        biржа = "📊 <b>Биржа:</b> АИ-95 %s ₽/т%s" % (
            esc(spaced(exch["ai95_spb_rub_t"])), (" (%s)" % trend_ru) if trend_ru else "")
        if exch.get("ai92_spb_rub_t"):
            biржа += ", АИ-92 %s ₽/т" % esc(spaced(exch["ai92_spb_rub_t"]))
        L.append(biржа)

    # Детали второго слоя (экспорт/розница/энергетика) — только если есть что сказать.
    detail_bits = []
    if nb.get("export_ban_gasoline"):
        detail_bits.append("экспорт бензина под запретом")
    blackouts = grid.get("blackout_regions") or []
    if blackouts:
        bo_txt = "; ".join("%s — %s" % (bo.get("region", ""),
                            {"rolling": "веерные отключения", "full": "блэкаут"}.get(bo.get("scope"), ""))
                            for bo in blackouts[:3])
        detail_bits.append("⚡ %s" % bo_txt)
    if detail_bits:
        L.append("<blockquote expandable>%s</blockquote>" % esc("; ".join(detail_bits)))
    L.append("")

    # ── Голоса (только реальная цитата) ──
    if voices:
        v0 = voices[0]
        quote = str(v0.get("quote", "")).strip()
        if len(quote) > 160:
            quote = quote[:157].rstrip() + "…"
        L.append('🗣 <i>«%s»</i> — %s' % (esc(quote), esc(v0.get("city", ""))))
        L.append("")

    # ── Ссылки ──
    site_page = data.get("site_page") or ("%s/news/%s" % (SITE, date_iso))
    L.append('👉 <a href="%s">Карта ударов</a> · <a href="%s">Сводка на сайте</a>' % (
        esc_attr(SITE), esc_attr(site_page)))

    text = "\n".join(L).strip()
    # Убираем возможные тройные пустые строки
    text = re.sub(r"\n{3,}", "\n\n", text)

    length = entity_len(text)
    if length <= CAPTION_HARD_MAX:
        mode = "caption"
        caption_or_text = text
        out_text = None
    else:
        mode = "split"
        caption_or_text = text  # используется как текстовое сообщение в split-режиме
        out_text = text
        if entity_len(out_text) > TEXT_HARD_MAX:
            out_text = _truncate_to(out_text, TEXT_HARD_MAX)
            caption_or_text = out_text

    return {"mode": mode, "caption_or_text": caption_or_text, "text": out_text, "headline": headline}


# ──────────────────────────────────────────────────────────────
# МОЛНИЯ
# ──────────────────────────────────────────────────────────────

def render_molniya(event):
    """event: {"headline", "city", "region", "target", "why", "confidence"
    ("confirmed"|"reported"), "sources": [...], "context": str, "url": SITE|custom}."""
    headline_raw = str(event.get("headline", ""))
    if len(headline_raw) > 70:
        headline = headline_raw[:70].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"
    else:
        headline = headline_raw
    city = event.get("city", "")
    region = event.get("region", "")
    target = event.get("target", "")
    why = event.get("why", "")
    confidence = event.get("confidence")
    sources = event.get("sources") or []
    context = event.get("context", "")
    url = event.get("url") or SITE

    L = ["🚨 <b>МОЛНИЯ · %s</b>" % esc(headline), ""]
    loc = city
    if region and region != city:
        loc = "%s, %s" % (city, region) if city else region
    L.append("📍 %s" % esc(loc))
    tgt_line = "🎯 %s" % esc(target)
    if why:
        tgt_line += " — %s" % esc(why)
    L.append(tgt_line)
    if confidence == "confirmed":
        conf_line = "✓ Подтверждено: %s" % esc(", ".join(sources)) if sources else "✓ Подтверждено"
    else:
        conf_line = "~ Ожидает подтверждения"
    L.append(conf_line)
    L.append("")
    if context:
        L.append(esc(context))
    L.append('👉 <a href="%s">Карта</a>' % esc_attr(url))

    text = "\n".join(L).strip()
    if entity_len(text) > MOLNIYA_MAX:
        text = _truncate_to(text, MOLNIYA_MAX)
    return text


# ──────────────────────────────────────────────────────────────
# БПЛА-АЛЕРТ
# ──────────────────────────────────────────────────────────────

def render_uav_alert(regions, since_msk=None, source="", cleared=False, cleared_at_msk=None):
    """regions: list[str]. since_msk/cleared_at_msk: 'HH:MM' строка или None (текущее МСК)."""
    if cleared:
        t = cleared_at_msk or now_msk().strftime("%H:%M")
        text = "✅ <b>Отбой</b> · %s · 🕐 %s МСК" % (esc(", ".join(regions)), esc(t))
    else:
        t = since_msk or now_msk().strftime("%H:%M")
        L = ["⚠️ <b>Опасность БПЛА</b> · %s" % esc(", ".join(regions))]
        src_part = " · 📡 %s" % esc(source) if source else ""
        L.append("🕐 с %s МСК%s" % (esc(t), src_part))
        L.append('👉 <a href="%s/radar">Радар</a>' % esc_attr(SITE))
        text = "\n".join(L)
    if entity_len(text) > UAV_ALERT_MAX:
        text = _truncate_to(text, UAV_ALERT_MAX)
    return text


# ──────────────────────────────────────────────────────────────
# СТРОКА ПОПОЛНЕНИЯ (update line)
# ──────────────────────────────────────────────────────────────

def render_update_line(update, kind="update"):
    """update: {"time_msk": "14:20", "text": "...", "molniya_url": None|str}.
    kind="molniya" — апдейт про молнию (со ссылкой)."""
    t = update.get("time_msk") or now_msk().strftime("%H:%M")
    if kind == "molniya" and update.get("molniya_url"):
        return '🔄 <b>%s МСК</b> — 🚨 <a href="%s">МОЛНИЯ: %s</a>' % (
            esc(t), esc_attr(update["molniya_url"]), esc(update.get("text", "")))
    return "🔄 <b>%s МСК</b> %s" % (esc(t), esc(update.get("text", "")))


# ──────────────────────────────────────────────────────────────
# SELFTEST
# ──────────────────────────────────────────────────────────────

def _selftest():
    ok_all = True

    def check(name, cond, extra=""):
        nonlocal ok_all
        status = "OK" if cond else "FAIL"
        if not cond:
            ok_all = False
        print("[%s] %s %s" % (status, name, extra))

    # 1. 912 знаков → caption
    strikes_small = [
        {"city": "Ярославль", "target": "ЯНОС", "date": "2026-07-06", "confidence": "confirmed",
         "detail": "Горит установка АВТ."},
        {"city": "Белгород", "target": "ТЭЦ", "date": "2026-07-06", "confidence": "reported"},
    ]
    small_data = {
        "strikes": strikes_small, "voices": [{"city": "Новороссийск", "quote": "Очередь 6 часов на заправке"}],
        "azs": [{"region": "Крым", "level": "critical"}],
        "exchange": {"ai95_spb_rub_t": 74250, "trend": "stable"},
        "fuel": {"national_balance": {"capacity_offline_pct": 12}, "refineries": [{"status": "partial"}]},
        "grid": {}, "date_iso": "2026-07-06",
    }
    r1 = render_briefing(small_data, kind="evening")
    ok1, reason1 = preflight(r1["caption_or_text"], CAPTION_HARD_MAX)
    check("912-char-ish briefing -> caption mode", r1["mode"] == "caption" and ok1,
          "len=%d mode=%s reason=%s" % (entity_len(r1["caption_or_text"]), r1["mode"], reason1))

    # 2. ~2200 знаков → split-mode
    many_strikes = [
        {"city": "Город%d" % i, "target": "Объект инфраструктуры номер %d с длинным названием" % i,
         "date": "2026-07-06", "confidence": "reported",
         "detail": "Подробное описание удара номер %d с деталями и техническими параметрами установки." % i}
        for i in range(12)
    ]
    big_data = dict(small_data)
    big_data["strikes"] = many_strikes
    big_data["voices"] = [{"city": "Новороссийск", "quote": "Очень длинная цитата про очереди на заправках которая тянется довольно долго и описывает ситуацию в деталях."}]
    big_data["grid"] = {"blackout_regions": [{"region": "Белгородская обл.", "scope": "rolling"}]}
    r2 = render_briefing(big_data, kind="morning")
    ok2, reason2 = preflight(r2["text"] or r2["caption_or_text"], TEXT_HARD_MAX)
    check("~2200-char briefing -> split mode", r2["mode"] == "split" and ok2,
          "len=%d mode=%s reason=%s" % (entity_len(r2["text"] or ""), r2["mode"], reason2))

    # 3. >4096 → сокращение (жёсткий кейс: очень много ударов)
    huge_strikes = many_strikes * 6
    huge_data = dict(big_data)
    huge_data["strikes"] = huge_strikes
    r3 = render_briefing(huge_data, kind="evening")
    text3 = r3["text"] or r3["caption_or_text"]
    ok3, reason3 = preflight(text3, TEXT_HARD_MAX)
    check(">4096-char briefing -> truncated within limit", entity_len(text3) <= TEXT_HARD_MAX and ok3,
          "len=%d ok=%s reason=%s" % (entity_len(text3), ok3, reason3))

    # 4. molniya
    molniya = render_molniya({
        "headline": "Удар по Омскому НПЗ — 2 500 км от границы",
        "city": "Омск", "region": "Омская область",
        "target": "Омский НПЗ — крупнейший в РФ (22+ млн т/год)",
        "why": "единственное производство крекинг-катализаторов",
        "confidence": "confirmed", "sources": ["NASA FIRMS", "два независимых канала"],
        "context": "Первый удар по НПЗ в Сибири за всю кампанию.",
    })
    ok4, reason4 = preflight(molniya, MOLNIYA_MAX)
    check("molniya renders within limit + preflight ok", ok4, "len=%d reason=%s" % (entity_len(molniya), reason4))

    # 5. uav alert
    alert = render_uav_alert(["Калужская", "Тульская", "Брянская обл."], since_msk="03:15", source="радар")
    ok5, reason5 = preflight(alert, UAV_ALERT_MAX)
    check("uav alert within limit", ok5, "len=%d reason=%s" % (entity_len(alert), reason5))

    # 6. preflight rejects bad tag / bare url
    bad = "<script>alert(1)</script> http://evil.example"
    ok6, reason6 = preflight(bad, 4096)
    check("preflight rejects disallowed tag/bare url", not ok6, "reason=%s" % reason6)

    print("\n%s" % ("ALL SELFTESTS PASSED" if ok_all else "SELFTEST FAILURES PRESENT"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print("Использование: python3 -m hermes.bot.render --selftest")
