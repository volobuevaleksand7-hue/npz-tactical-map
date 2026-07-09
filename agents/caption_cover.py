#!/usr/bin/env python3
"""
caption_cover.py — накладывает читаемую подпись на обложку новостной сводки.

Базовое изображение (город + событие) генерит image_gen; русский текст image_gen
рисует плохо, поэтому подпись кладём здесь через Pillow брендовым шрифтом поверх
градиентной подложки — легко читается и в едином стиле для сайта и Telegram.

CLI:  python3 agents/caption_cover.py <in.png> <out.png> "<Город>" "<событие>" "<дата_rus>"
API:  caption_cover(in_path, out_path, city, event, date_rus)
       pick_top_strike(strikes_path, hours=24) -> dict | None
"""
import json
import sys
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
CREAM = (251, 248, 241)
AMBER = (255, 206, 107)
DIM = (214, 208, 196)
import platform as _plat
if _plat.system() == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
else:
    # Linux VPS — Liberation Sans (metrically compatible with Arial)
    FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def _fit_font(draw, text, path, max_w, start, min_size=28):
    size = start
    while size > min_size:
        f = ImageFont.truetype(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return ImageFont.truetype(path, min_size)


_LARGE_NPZ_CITIES = {"Омск", "Куйбышев", "Рязань", "Сызрань", "Ачинск"}


def _is_npz_strike(target):
    t = str(target or "").lower()
    return "нпз" in t or "нефтеперерабатыва" in t


def _strike_score(strike, max_date):
    """Приоритет обложки дня: НПЗ-удар > крупный НПЗ-город > confirmed > самая свежая дата.
    Тот же принцип, что и в select_event.py/build-covers.py::lead_score — просто адаптирован
    под окно в часах вместо фиксированных «последних 2 дат»."""
    score = 0
    if _is_npz_strike(strike.get("target")):
        score += 4
    if strike.get("city") in _LARGE_NPZ_CITIES:
        score += 3
    if strike.get("confidence") == "confirmed":
        score += 2
    if strike.get("date") == max_date:
        score += 1
    return score


def pick_top_strike(strikes_path, hours=24):
    """Выбрать один самый «обложко-достойный» удар из strikes.json за последние `hours`.

    strikes.json хранит только дату (без времени дня), поэтому окно в часах здесь —
    округление до целых календарных дат (hours=24 → сегодняшняя дата по данным,
    hours=48 → сегодня+вчера и т.д.), а не точная почасовая отсечка.
    Возвращает dict с ключами city/target/date/confidence/score, либо None, если
    strikes.json не читается или в окне нет ударов.
    """
    try:
        with open(strikes_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None

    strikes = data.get("strikes") or []
    all_dates = sorted({s.get("date") for s in strikes if s.get("date")}, reverse=True)
    if not all_dates:
        return None

    days = max(1, round(hours / 24))
    target_dates = set(all_dates[:days])
    max_date = all_dates[0]

    candidates = [s for s in strikes if s.get("date") in target_dates]
    if not candidates:
        return None

    best = max(candidates, key=lambda s: (_strike_score(s, max_date), s.get("date", "")))
    return {
        "city": best.get("city") or "Россия",
        "target": best.get("target") or best.get("title") or "атака",
        "date": best.get("date"),
        "confidence": best.get("confidence") or "reported",
        "score": _strike_score(best, max_date),
    }


def caption_cover(in_path, out_path, city, event, date_rus):
    img = Image.open(in_path).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    # нижняя градиентная подложка для читаемости подписи
    scrim = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, (y - H * 0.5) / (H * 0.5))
        scrim.putpixel((0, y), int(220 * (t ** 1.6)))
    scrim = scrim.resize((W, H))
    black = Image.new("RGB", (W, H), (4, 20, 11))
    img = Image.composite(black, img, scrim)

    d = ImageDraw.Draw(img)
    pad = 48

    # верхний бейдж-«кикер»
    kicker = "ТОПЛИВНЫЙ ФРОНТ РФ"
    fk = ImageFont.truetype(FONT_BOLD, 24)
    kw = d.textlength(kicker, font=fk)
    d.rounded_rectangle([pad - 12, pad - 8, pad + kw + 12, pad + 30], radius=8,
                        fill=(4, 20, 11))
    d.text((pad, pad - 4), kicker, font=fk, fill=AMBER)

    # город (крупно) + событие (помельче) + дата — прижаты к низу
    f_city = _fit_font(d, city, FONT_BOLD, W - pad * 2, 82, 44)
    f_event = _fit_font(d, event, FONT_REG, W - pad * 2, 42, 26)
    f_date = ImageFont.truetype(FONT_BOLD, 26)

    city_h = f_city.getbbox(city)[3]
    event_h = f_event.getbbox(event)[3]
    y_date = H - pad - 30
    y_event = y_date - event_h - 18
    y_city = y_event - city_h - 6

    d.text((pad, y_city), city, font=f_city, fill=CREAM)
    d.text((pad, y_event), event, font=f_event, fill=DIM)
    # дата — янтарным, с точкой-разделителем
    d.text((pad, y_date), "● " + date_rus + " 2026", font=f_date, fill=AMBER)

    img.save(out_path, "PNG")
    return out_path


def _selftest_pick_top_strike():
    """ponytail: assert-based smoke test (this repo has no pytest suite for agents/*.py) —
    proves pick_top_strike() actually picks the NPZ-hit over a same-day non-NPZ strike and
    ignores strikes outside the requested window, instead of raising ImportError (audit C4)."""
    import tempfile
    import os as _os

    fixture = {
        "strikes": [
            {"date": "2026-07-08", "city": "Тверь", "target": "жилой дом", "confidence": "confirmed"},
            {"date": "2026-07-09", "city": "Омск", "target": "Омский НПЗ", "confidence": "reported"},
            {"date": "2026-07-09", "city": "Тверь", "target": "склад", "confidence": "confirmed"},
            {"date": "2026-06-01", "city": "Курск", "target": "Курский НПЗ", "confidence": "confirmed"},
        ]
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(fixture, f)

        top = pick_top_strike(path, hours=24)
        assert top is not None, "expected a strike, got None"
        assert top["date"] == "2026-07-09", top
        assert top["city"] == "Омск", "NPZ hit should outrank confirmed non-NPZ hit: %r" % top
        assert set(top) >= {"city", "target", "date", "confidence", "score"}, top

        old = pick_top_strike(path, hours=1)  # 1h window -> only the freshest date
        assert old["city"] == "Омск", old

        assert pick_top_strike("/no/such/file.json") is None
        assert pick_top_strike(path.replace(".json", "-missing.json")) is None
    finally:
        _os.unlink(path)
    print("OK: pick_top_strike selftest passed (NPZ-priority, window, missing-file cases)")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest_pick_top_strike()
    elif len(sys.argv) != 6:
        print("usage: caption_cover.py <in.png> <out.png> <city> <event> <date_rus>", file=sys.stderr)
        print("       caption_cover.py --selftest", file=sys.stderr)
        sys.exit(1)
    else:
        caption_cover(*sys.argv[1:6])
        print("wrote", sys.argv[2])
