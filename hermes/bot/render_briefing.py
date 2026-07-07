#!/usr/bin/env python3
# render_briefing.py — утренняя/вечерняя тактическая сводка «Топливный фронт РФ».
# Строит tall-form SVG и конвертит в PNG через cairosvg.
# Данные берутся из data/*.json — тот же pipeline, что и broadcast.py.
#
# Публичный API:
#   render_briefing(mode: str, out_path: str) -> str
#   mode = "morning" | "evening"
#
# Самотест: python3 render_briefing.py --demo /tmp/briefing_demo.png
import json, os, sys, datetime, html

REPO = os.environ.get("NPZ_REPO", "/root/npz-tactical-map")
DATA = os.path.join(REPO, "data")

W = 1200
PADDING = 60
CONTENT_W = W - 2 * PADDING

# --- Палитра (из render_card.py + расширения) ---
BG_DARK    = "#04140b"
BG_DARK2   = "#0a2416"
BG_LIGHT   = "#fbf8f1"
BG_LIGHT2  = "#f3eee2"
AMBER      = "#e0b020"
AMBER2     = "#ffce6b"
RED        = "#ff5247"
GREEN      = "#4ade80"
GREEN_DIM  = "#22c55e"
ORANGE     = "#f59e0b"
YELLOW     = "#facc15"
CREAM      = "#fbf8f1"
CREAM2     = "#f3eee2"
DIM_WHITE  = "#a8a29e"
FONT       = "'PT Sans','DejaVu Sans','Arial',sans-serif"
FONT_MONO  = "'PT Mono','DejaVu Sans Mono','Courier New',monospace"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def load(fn, default=None):
    try:
        return json.load(open(os.path.join(DATA, fn), encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def rudate(iso):
    MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        y, m, d = str(iso)[:10].split("-")
        return "%d %s" % (int(d), MONTHS[int(m)])
    except Exception:
        return str(iso or "")


def wrap(text, max_chars):
    words = str(text or "").split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ──────────────────────────────────────────────
# Data aggregation
# ──────────────────────────────────────────────

DEFICIT_LEVELS = {"strained", "limited", "severe", "critical"}
LEVEL_RU = {
    "calm": "🟢 спокойно",
    "strained": "🟡 перебои",
    "limited": "🟠 лимиты",
    "severe": "🔴 талоны/QR",
    "critical": "⛔ сухо",
}
LEVEL_SHORT = {
    "calm": "спокойно",
    "strained": "перебои",
    "limited": "лимиты",
    "severe": "талоны/QR",
    "critical": "сухо",
}
LEVEL_EMOJI = {
    "calm": "🟢",
    "strained": "🟡",
    "limited": "🟠",
    "severe": "🔴",
    "critical": "⛔",
}


def gather_data(mode):
    """Собирает все данные для сводки. Возвращает dict."""
    azs = load("fuel-availability.json") or {}
    strikes_data = load("strikes.json") or {}
    grid = load("grid-state.json") or {}
    voices_data = load("fuel-voices.json") or {}
    fuel = load("fuel-state.json") or {}

    # --- Биржа ---
    exch = azs.get("exchange", {})

    # --- Удары ---
    strikes = strikes_data.get("strikes", [])
    cutoff_7d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    cutoff_24h = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d")
    strikes_7d = [s for s in strikes if str(s.get("date", ""))[:10] >= cutoff_7d]
    strikes_24h = [s for s in strikes if str(s.get("date", ""))[:10] >= cutoff_24h]

    # --- АЗС ---
    regions = azs.get("regions", [])
    # Группируем по level
    by_level = {}
    for r in regions:
        lv = r.get("level", "calm")
        by_level.setdefault(lv, []).append(r)
    # Сортируем: severe > limited > strained > calm
    level_order = ["critical", "severe", "limited", "strained", "calm"]
    sorted_regions = []
    for lv in level_order:
        if lv in by_level:
            sorted_regions.extend(sorted(by_level[lv], key=lambda x: x.get("region", "")))

    n_deficit = sum(1 for r in regions if r.get("level") in DEFICIT_LEVELS)
    n_total = len(regions)

    # --- Электричество ---
    blackout_regions = grid.get("blackout_regions", [])
    damaged_subs = [s for s in grid.get("substations", []) if s.get("status") == "damaged"]
    n_damaged = len(damaged_subs)

    # --- Голоса ---
    voices = voices_data.get("voices", [])

    # --- НПЗ ---
    refineries = fuel.get("refineries", [])
    down_count = sum(1 for r in refineries if r.get("status") == "down")
    partial_count = sum(1 for r in refineries if r.get("status") == "partial")
    nb = fuel.get("national_balance", {})

    # --- Последние события ---
    recent_events = fuel.get("events", [])[:3] if fuel.get("events") else []

    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = rudate(now.strftime("%Y-%m-%d"))
    time_str = now.strftime("%H:%M UTC")

    return {
        "mode": mode,
        "date_str": date_str,
        "time_str": time_str,
        "exchange": exch,
        "strikes_7d": len(strikes_7d),
        "strikes_24h": len(strikes_24h),
        "strikes_latest": strikes[:4],
        "regions": sorted_regions,
        "n_deficit": n_deficit,
        "n_total": n_total,
        "blackout_regions": blackout_regions,
        "n_damaged_subs": n_damaged,
        "voices": [v for v in voices if _is_ru(v.get("quote"))][:3],
        "down_count": down_count,
        "partial_count": partial_count,
        "throughput_shortfall": nb.get("throughput_shortfall_pct"),
        "capacity_offline_pct": nb.get("capacity_offline_pct"),
        "export_ban": nb.get("export_ban_gasoline"),
    }


def _is_ru(q):
    q = str(q or "")
    cyr = sum('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in q)
    lat = sum('a' <= c.lower() <= 'z' for c in q)
    return cyr >= lat


# ──────────────────────────────────────────────
# SVG building
# ──────────────────────────────────────────────

class SvgBuilder:
    def __init__(self):
        self.y = 0  # current vertical cursor
        self.parts = []

    def rect(self, x, y, w, h, rx=0, fill=None, stroke=None, stroke_width=1, opacity=1.0, stroke_opacity=1.0):
        attrs = 'x="%d" y="%d" width="%d" height="%d"' % (x, y, w, h)
        if rx:
            attrs += ' rx="%d"' % rx
        if fill:
            attrs += ' fill="%s"' % fill
        if opacity < 1:
            attrs += ' fill-opacity="%s"' % opacity
        if stroke:
            attrs += ' stroke="%s" stroke-width="%d"' % (stroke, stroke_width)
            if stroke_opacity < 1:
                attrs += ' stroke-opacity="%s"' % stroke_opacity
        self.parts.append('<rect %s/>' % attrs)

    def text(self, x, y, text, size=24, fill=CREAM, font=FONT, weight="400",
             anchor="start", style="", opacity=1.0, letter_spacing=0):
        attrs = 'x="%d" y="%d" font-family=%s font-size="%d" font-weight="%s" fill="%s"' % (
            x, y, '"%s"' % font, size, weight, fill)
        if anchor != "start":
            attrs += ' text-anchor="%s"' % anchor
        if opacity < 1:
            attrs += ' fill-opacity="%s"' % opacity
        if letter_spacing:
            attrs += ' letter-spacing="%d"' % letter_spacing
        if style:
            attrs += ' %s' % style
        self.parts.append('<text %s>%s</text>' % (attrs, esc(text)))

    def line(self, x1, y1, x2, y2, stroke=AMBER, width=1, opacity=0.2):
        self.parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" '
                          'stroke-width="%d" stroke-opacity="%s"/>' % (x1, y1, x2, y2, stroke, width, opacity))


def _header_block(b, data):
    """Тёмная шапка: kicker, headline, 3 колонки статов."""
    mode_label = "УТРЕННЯЯ СВОДКА" if data["mode"] == "morning" else "ВЕЧЕРНЯЯ СВОДКА"
    header_h = 260

    # Dark background
    b.rect(20, 20, W - 40, header_h, rx=18, fill=BG_DARK, stroke=AMBER, stroke_width=2, stroke_opacity=0.35)

    # Kicker
    b.text(PADDING, 72, "СВОДКА · %s · КАРТА АЗС ОНЛАЙН" % mode_label,
           size=20, fill=AMBER, weight="700", letter_spacing=2)

    # Headline
    b.text(PADDING, 126, "Топливный фронт РФ", size=52, fill=CREAM, weight="800")
    b.text(PADDING, 164, "за %s · %s" % (data["date_str"], data["time_str"]),
           size=24, fill=AMBER2, weight="700")

    # 3 стат-колонки
    stats_top = 195
    col_w = CONTENT_W // 3

    stats = []
    exch = data["exchange"]
    if exch.get("ai95_spb_rub_t"):
        trend = {"spike": "скачок", "rising": "↑ рост", "falling": "↓ спад",
                 "stable": "→ стабильно"}.get(exch.get("trend"), "")
        stats.append({"value": "{:,} ₽/т".format(exch["ai95_spb_rub_t"]).replace(",", " "),
                      "label": "Биржа АИ-95 %s" % trend,
                      "color": RED if exch.get("trend") in ("spike", "rising") else AMBER2})
    stats.append({"value": str(data["strikes_7d"]),
                  "label": "Ударов за 7 дней",
                  "color": RED if data["strikes_7d"] > 5 else AMBER2})
    stats.append({"value": "%d из %d" % (data["n_deficit"], data["n_total"]),
                  "label": "Регионов с дефицитом",
                  "color": RED if data["n_deficit"] > 20 else AMBER2})

    for i, s in enumerate(stats):
        cx = PADDING + col_w * i + col_w // 2
        b.text(cx, stats_top, s["value"], size=42, fill=s["color"], weight="700", anchor="middle")
        b.text(cx, stats_top + 30, s["label"], size=18, fill=CREAM2, anchor="middle", opacity=0.75)
        if i:
            dx = PADDING + col_w * i
            b.line(dx, stats_top - 25, dx, stats_top + 25, opacity=0.2)

    b.y = header_h + 30
    return header_h


def _section_header(b, emoji, title, y=None):
    """Заголовок секции в body."""
    if y is not None:
        b.y = y
    b.text(PADDING, b.y + 28, "%s %s" % (emoji, title), size=28, fill="#1a1a1a", weight="800")
    b.line(PADDING, b.y + 38, W - PADDING, b.y + 38, stroke="#d4d0c8", opacity=0.5)
    b.y += 50


def _azs_section(b, data):
    """Секция АЗС: таблица регионов."""
    _section_header(b, "⛽", "АЗС — ситуация по регионам")

    regions = data["regions"]
    if not regions:
        b.text(PADDING, b.y + 20, "Нет данных", size=20, fill="#888")
        b.y += 40
        return

    # Показываем severe и limited (макс 12 регионов)
    show = [r for r in regions if r.get("level") in ("critical", "severe", "limited")]
    if len(show) > 12:
        show = show[:12]
    remaining = len(regions) - len(show)

    # Таблица: 2 колонки
    rows_per_col = (len(show) + 1) // 2
    col_w = CONTENT_W // 2
    row_h = 38

    for idx, r in enumerate(show):
        col = idx // rows_per_col if rows_per_col else 0
        row = idx % rows_per_col if rows_per_col else idx
        x = PADDING + col * col_w
        y = b.y + row * row_h

        lv = r.get("level", "calm")
        emoji = LEVEL_EMOJI.get(lv, "⚪")
        region = r.get("region", "")
        level_text = LEVEL_SHORT.get(lv, lv)

        # Определяем лимит
        limits = []
        for net in (r.get("networks") or []):
            ll = net.get("limit_l")
            if ll and ll not in limits:
                limits.append(ll)
        limit_str = ""
        if limits:
            min_l = min(limits)
            max_l = max(limits)
            if min_l == max_l:
                limit_str = " ≤%dл" % min_l
            else:
                limit_str = " ≤%d–%dл" % (min_l, max_l)

        # Цена
        price_str = ""
        ai95 = r.get("ai95_price_rub")
        if ai95:
            price_str = " · %.0f₽/л" % ai95

        line_text = "%s %s — %s%s%s" % (emoji, region, level_text, limit_str, price_str)
        # Обрезаем если слишком длинное
        if len(line_text) > 58:
            line_text = line_text[:56] + "…"

        fill = "#1a1a1a" if lv in ("severe", "critical") else "#3a3a3a"
        b.text(x + 8, y + 18, line_text, size=18, fill=fill, weight="400")

    b.y += rows_per_col * row_h + 10

    # Остальные регионы
    if remaining > 0:
        calm_count = sum(1 for r in data["regions"] if r.get("level") == "calm")
        strained_count = sum(1 for r in data["regions"] if r.get("level") == "strained")
        parts = []
        if strained_count:
            parts.append("%d — перебои" % strained_count)
        if calm_count:
            parts.append("%d — спокойно" % calm_count)
        note = "Ещё %d рег.: %s" % (remaining, ", ".join(parts)) if parts else "Ещё %d рег." % remaining
        b.text(PADDING, b.y + 16, note, size=16, fill="#888", weight="400")
        b.y += 30


def _exchange_section(b, data):
    """Биржа: курсы."""
    exch = data["exchange"]
    if not exch.get("ai95_spb_rub_t"):
        return
    _section_header(b, "💹", "Биржа СПбМТСБ")

    lines = []
    if exch.get("ai95_spb_rub_t"):
        lines.append("АИ-95: %s ₽/т" % "{:,}".format(exch["ai95_spb_rub_t"]).replace(",", " "))
    if exch.get("ai92_spb_rub_t"):
        lines.append("АИ-92: %s ₽/т" % "{:,}".format(exch["ai92_spb_rub_t"]).replace(",", " "))
    if exch.get("diesel_spb_rub_t"):
        lines.append("ДТ: %s ₽/т" % "{:,}".format(exch["diesel_spb_rub_t"]).replace(",", " "))

    trend_ru = {"spike": "⚡ скачок", "rising": "📈 рост", "falling": "📉 спад",
                "stable": "➡️ стабильно"}.get(exch.get("trend"), "")

    text = " · ".join(lines)
    if trend_ru:
        text += " · %s" % trend_ru
    b.text(PADDING, b.y + 18, text, size=20, fill="#1a1a1a", weight="400")
    b.y += 36


def _npz_section(b, data):
    """Секция НПЗ: сколько выбито."""
    if not data["down_count"] and not data["throughput_shortfall"]:
        return
    _section_header(b, "🏭", "Нефтепереработка")

    parts = []
    if data["down_count"]:
        parts.append("%d НПЗ остановлены полностью" % data["down_count"])
    if data["partial_count"]:
        parts.append("%d — частично" % data["partial_count"])
    if data["throughput_shortfall"]:
        parts.append("недобор переработки ~%d%%" % data["throughput_shortfall"])
    if data["export_ban"]:
        parts.append("экспорт бензина запрещён")

    b.text(PADDING, b.y + 18, " · ".join(parts), size=18, fill="#3a3a3a", weight="400")
    b.y += 36


def _grid_section(b, data):
    """Секция электричества: блэкауты."""
    blackouts = data["blackout_regions"]
    if not blackouts and not data["n_damaged_subs"]:
        return
    _section_header(b, "⚡", "Электричество")

    if blackouts:
        for bo in blackouts[:4]:
            region = bo.get("region", "")
            scope = bo.get("scope", "")
            pop = bo.get("affected_population", "")
            since = bo.get("since", "")
            scope_ru = {"rolling": "веерные отключения", "full": "полный блэкаут",
                        "partial": "частичные отключения"}.get(scope, scope)

            line = "🔴 %s — %s" % (region, scope_ru)
            if pop:
                line += " (%s)" % pop
            if since:
                line += " с %s" % rudate(since)
            if len(line) > 80:
                line = line[:78] + "…"
            b.text(PADDING, b.y + 18, line, size=17, fill="#1a1a1a", weight="400")
            b.y += 28

    if data["n_damaged_subs"]:
        b.text(PADDING, b.y + 16,
               "Повреждено подстанций/объектов: %d" % data["n_damaged_subs"],
               size=16, fill="#888", weight="400")
        b.y += 28

    b.y += 8


def _strikes_section(b, data):
    """Последние удары."""
    latest = data["strikes_latest"]
    if not latest:
        return
    _section_header(b, "💥", "Удары (последние сутки: %d)" % data["strikes_24h"])

    for s in latest[:4]:
        city = s.get("city", "")
        target = str(s.get("target", "")).split("(")[0].split("—")[0].strip()[:50]
        conf = {"confirmed": "✓", "reported": "·", "rumored": "?"}.get(s.get("confidence"), "")
        line = "• %s — %s %s" % (city, target, conf)
        if len(line) > 80:
            line = line[:78] + "…"
        b.text(PADDING, b.y + 18, line, size=17, fill="#3a3a3a", weight="400")
        b.y += 26

    b.y += 8


def _voices_section(b, data):
    """Голоса людей."""
    voices = data["voices"]
    if not voices:
        return
    _section_header(b, "🗣", "Люди говорят")

    for v in voices[:3]:
        city = v.get("city", "")
        quote = str(v.get("quote", "")).strip()
        if len(quote) > 140:
            quote = quote[:137] + "…"

        # Quote box
        q_lines = wrap(quote, 60)
        box_h = len(q_lines) * 24 + 40
        b.rect(PADDING, b.y + 4, CONTENT_W, box_h, rx=12, fill=BG_DARK2, opacity=0.08)

        # Кавычка «
        b.text(PADDING + 14, b.y + 36, "«", size=36, fill=AMBER, weight="700", opacity=0.5)
        # Текст цитаты
        for li, ln in enumerate(q_lines):
            b.text(PADDING + 52, b.y + 26 + li * 24, ln, size=17, fill="#2a2a2a",
                   weight="400", style='font-style="italic"')
        # Город
        last_line_y = b.y + 26 + len(q_lines) * 24
        b.text(PADDING + 52, last_line_y + 4, "— %s" % city, size=16, fill=AMBER, weight="700")

        b.y += box_h + 12


def _footer(b):
    """Футер."""
    b.line(PADDING, b.y + 10, W - PADDING, b.y + 10, stroke="#d4d0c8", opacity=0.4)
    b.text(PADDING, b.y + 32, "Источник: открытые данные карты · OSINT-агрегация · Не является офиц. информацией",
           size=14, fill="#999", weight="400")
    b.text(W - PADDING, b.y + 32, "npz-tactical-map.vercel.app",
           size=14, fill="#999", weight="400", anchor="end")
    b.y += 50


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def build_briefing_svg(mode="morning"):
    """Строит SVG-строку для сводки mode='morning'|'evening'."""
    data = gather_data(mode)
    b = SvgBuilder()

    # 1. Шапка
    _header_block(b, data)

    # 2. Body background (light) — рисуем позже, но нужна высота
    body_start = b.y

    # 3. Секции body
    _azs_section(b, data)
    _exchange_section(b, data)
    _npz_section(b, data)
    _grid_section(b, data)
    _strikes_section(b, data)
    _voices_section(b, data)
    _footer(b)

    total_h = b.y + 30

    # Собираем SVG
    svg = []
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
               % (W, total_h, W, total_h))

    # Background
    svg.append('<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#e8e4d8"/><stop offset="1" stop-color="%s"/>'
               '</linearGradient></defs>' % BG_LIGHT)
    svg.append('<rect width="%d" height="%d" fill="url(#bg)"/>' % (W, total_h))

    # Body background (light card)
    svg.append('<rect x="20" y="%d" width="%d" height="%d" rx="18" fill="%s"/>'
               % (body_start - 10, W - 40, total_h - body_start + 20, BG_LIGHT))

    # Добавляем все элементы
    svg.extend(b.parts)

    svg.append('</svg>')
    return "\n".join(svg)


def render_briefing(mode="morning", out_path=None):
    """Рендерит PNG-файл сводки. Возвращает путь."""
    import cairosvg
    if out_path is None:
        out_path = os.path.join(os.path.expanduser("~"), ".npz-bot", "briefing-%s.png" % mode)
    svg = build_briefing_svg(mode)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=out_path,
                     output_width=W)
    return out_path


if __name__ == "__main__":
    mode = "morning"
    out = "/tmp/briefing_morning.png"
    args = sys.argv[1:]
    if "--evening" in args:
        mode = "evening"
        out = "/tmp/briefing_evening.png"
    if "--demo" in args:
        i = args.index("--demo")
        if i + 1 < len(args):
            out = args[i + 1]
    print(render_briefing(mode, out))
