#!/usr/bin/env python3
# render_card.py — брендированная карточка-сводка для канала «Топливный фронт РФ».
# Строит SVG и конвертит в PNG через cairosvg (без браузера, без сети, без секретов).
#
# Публичный API:
#   render_card(payload: dict, out_path: str) -> str
# payload = {
#   "date_str": "4 июля",
#   "headline": "Топливный фронт РФ",
#   "stats": [{"label": "...", "value": "..."}, ...],   # 1..3
#   "quote": {"city": "Москва", "text": "..."} | None,
# }
#
# Самотест: python3 render_card.py --demo /tmp/card_demo.png
import sys, html

W, H = 1200, 630
BG      = "#04140b"
CREAM   = "#fbf8f1"
CREAM2  = "#f3eee2"
AMBER   = "#e0b020"
AMBER2  = "#ffce6b"
RED     = "#ff5247"
FONT    = "'PT Sans','DejaVu Sans','Arial',sans-serif"


def esc(s):
    return html.escape(str(s or ""), quote=True)


def wrap(text, max_chars):
    """Простой перенос по словам."""
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


def _stat_block(stats, dy=0):
    """До 3 колонок: крупное значение + мелкая подпись. dy — сдвиг блока по вертикали
    (используется, когда цитаты нет и контент центрируется в карточке)."""
    n = len(stats)
    if not n:
        return ""
    top = 250 + dy
    rule_y = top - 40
    parts = ['<line x1="60" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity="0.15"/>'
             % (rule_y, W - 60, rule_y, AMBER)]

    if n == 1:
        # Один стат: не теряем его по центру пустого канваса — прижимаем к левому
        # полю (как заголовок/kicker) и даём ему больше веса как «герою» карточки.
        s = stats[0]
        rawval = str(s.get("value", ""))
        if len(rawval) > 16:
            rawval = rawval[:15].rstrip() + "…"
        val = esc(rawval)
        lab = esc(s.get("label", ""))
        color = RED if "удар" in str(s.get("label", "")).lower() else AMBER2
        vsize = 72 if len(rawval) <= 10 else (56 if len(rawval) <= 14 else 42)
        parts.append(
            '<text x="60" y="%d" text-anchor="start" font-family=%s font-size="%d" '
            'font-weight="700" fill="%s">%s</text>' % (top, '"%s"' % FONT, vsize, color, val)
        )
        parts.append(
            '<text x="60" y="%d" text-anchor="start" font-family=%s font-size="24" '
            'fill="%s" fill-opacity="0.75">%s</text>' % (top + 42, '"%s"' % FONT, CREAM2, lab)
        )
        return "\n".join(parts)

    col_w = (W - 120) // n
    for i, s in enumerate(stats):
        cx = 60 + col_w * i + col_w // 2
        rawval = str(s.get("value", ""))
        if len(rawval) > 16:
            rawval = rawval[:15].rstrip() + "…"
        val = esc(rawval)
        lab = esc(s.get("label", ""))
        # «ударов» подсветим красным, остальное — янтарным
        color = RED if "удар" in str(s.get("label", "")).lower() else AMBER2
        # адаптивный размер значения под длину
        vsize = 64 if len(rawval) <= 8 else (48 if len(rawval) <= 12 else 38)
        parts.append(
            '<text x="%d" y="%d" text-anchor="middle" font-family=%s font-size="%d" '
            'font-weight="700" fill="%s">%s</text>' % (cx, top, '"%s"' % FONT, vsize, color, val)
        )
        parts.append(
            '<text x="%d" y="%d" text-anchor="middle" font-family=%s font-size="24" '
            'fill="%s" fill-opacity="0.75">%s</text>' % (cx, top + 42, '"%s"' % FONT, CREAM2, lab)
        )
        if i:  # разделитель слева от колонки
            dx = 60 + col_w * i
            parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity="0.2"/>'
                         % (dx, top - 40, dx, top + 35, AMBER))
    return "\n".join(parts)


def _quote_block(quote):
    if not quote or not quote.get("text"):
        return ""
    lines = wrap(quote.get("text", ""), 52)[:2]
    if len(wrap(quote.get("text", ""), 52)) > 2:
        lines[-1] = lines[-1].rstrip() + "…"
    y0 = 430
    parts = ['<rect x="60" y="%d" width="%d" height="150" rx="14" fill="#0a2416" '
             'fill-opacity="0.6" stroke="%s" stroke-opacity="0.25"/>' % (y0, W - 120, AMBER)]
    parts.append('<text x="88" y="%d" font-family=%s font-size="70" font-weight="700" '
                 'fill="%s" fill-opacity="0.5">«</text>' % (y0 + 62, '"%s"' % FONT, AMBER))
    ty = y0 + 52
    for ln in lines:
        parts.append('<text x="150" y="%d" font-family=%s font-size="30" font-style="italic" '
                     'fill="%s">%s</text>' % (ty, '"%s"' % FONT, CREAM, esc(ln)))
        ty += 40
    parts.append('<text x="150" y="%d" font-family=%s font-size="24" font-weight="700" '
                 'fill="%s">— %s</text>' % (ty + 4, '"%s"' % FONT, AMBER2, esc(quote.get("city", ""))))
    return "\n".join(parts)


def build_svg(payload):
    headline = esc(payload.get("headline", "Топливный фронт РФ"))
    date_str = esc(payload.get("date_str", ""))
    stats = payload.get("stats", []) or []
    quote = payload.get("quote")

    # Когда цитаты нет, шапка+статы иначе повисают у верхнего края, оставляя
    # пустой канвас до футера. Центрируем весь блок по вертикали в оставшемся
    # пространстве карточки; если цитата есть — она сама заполняет низ, сдвиг не нужен.
    dy = 0
    if not quote:
        content_bottom = 300 if stats else 202
        zone_bottom = 536  # футер начинается на H-34=596, оставляем отступ
        dy = max(0, (zone_bottom - content_bottom) // 2)

    svg = []
    svg.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H))
    svg.append('<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#0a2013"/><stop offset="1" stop-color="%s"/>'
               '</linearGradient></defs>' % BG)
    svg.append('<rect width="%d" height="%d" fill="url(#bg)"/>' % (W, H))
    svg.append('<rect x="10" y="10" width="%d" height="%d" rx="18" fill="none" stroke="%s" '
               'stroke-opacity="0.35" stroke-width="2"/>' % (W - 20, H - 20, AMBER))
    # kicker
    svg.append('<text x="60" y="%d" font-family=%s font-size="26" font-weight="700" '
               'letter-spacing="3" fill="%s">СВОДКА · КАРТА АЗС ОНЛАЙН</text>' % (80 + dy, '"%s"' % FONT, AMBER))
    # headline + date (автоусадка длинного заголовка, чтобы не вылезал за 1200px)
    raw_headline = str(payload.get("headline", "Топливный фронт РФ"))
    hsize = 58 if len(raw_headline) <= 24 else (48 if len(raw_headline) <= 32 else 40)
    if len(raw_headline) > 42:
        headline = esc(raw_headline[:41].rstrip() + "…")
    svg.append('<text x="60" y="%d" font-family=%s font-size="%d" font-weight="800" '
               'fill="%s">%s</text>' % (150 + dy, '"%s"' % FONT, hsize, CREAM, headline))
    svg.append('<text x="60" y="%d" font-family=%s font-size="30" font-weight="700" '
               'fill="%s">за %s</text>' % (192 + dy, '"%s"' % FONT, AMBER2, date_str))
    svg.append(_stat_block(stats, dy))
    svg.append(_quote_block(quote))
    # footer
    svg.append('<text x="%d" y="%d" text-anchor="end" font-family=%s font-size="22" '
               'fill="%s" fill-opacity="0.6">npz-tactical-map.vercel.app</text>'
               % (W - 60, H - 34, '"%s"' % FONT, CREAM2))
    svg.append('</svg>')
    return "\n".join(svg)


def render_card(payload, out_path):
    import cairosvg
    svg = build_svg(payload or {})
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=out_path,
                     output_width=W, output_height=H)
    return out_path


if __name__ == "__main__":
    out = "/tmp/card_demo.png"
    if "--demo" in sys.argv:
        i = sys.argv.index("--demo")
        if i + 1 < len(sys.argv):
            out = sys.argv[i + 1]
    demo = {
        "date_str": "4 июля",
        "headline": "Топливный фронт РФ",
        "stats": [
            {"label": "Биржа АИ-95", "value": "74 250 ₽/т"},
            {"label": "Ударов за неделю", "value": "3"},
            {"label": "Регионов с дефицитом", "value": "12"},
        ],
        "quote": {"city": "Москва", "text": "Страна добывает нефть, а бензина нет. Как это вообще возможно?"},
    }
    print(render_card(demo, out))
