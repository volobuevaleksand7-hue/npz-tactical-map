#!/usr/bin/env python3
"""
caption_cover.py — накладывает читаемую подпись на обложку новостной сводки.

Базовое изображение (город + событие) генерит image_gen; русский текст image_gen
рисует плохо, поэтому подпись кладём здесь через Pillow брендовым шрифтом поверх
градиентной подложки — легко читается и в едином стиле для сайта и Telegram.

CLI:  python3 agents/caption_cover.py <in.png> <out.png> "<Город>" "<событие>" "<дата_rus>"
API:  caption_cover(in_path, out_path, city, event, date_rus)
"""
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
    # дата — янтарным, с точкой-разделителем; date_rus уже с годом (контракт callers)
    d.text((pad, y_date), "● " + date_rus, font=f_date, fill=AMBER)

    img.save(out_path, "PNG")
    return out_path


# --- lead strike selection (PIL-fallback cover) ---------------------------
# ponytail: константы дублируют hermes/scripts/build-covers.py — маленький дуб
# лучше, чем импорт модуля из другого каталога через оба дерева. Правишь один
# список ключей — синхронизируй второй.
from datetime import datetime, timedelta

_REF = ("нпз", "нефт", "терминал", "переработ", "нефтебаз", "нефтехим", "гпз", "перекачк")
_GRID = ("тэц", "тэс", "грэс", "подстанц", "энергет", "электро", "водоснаб")


def _classify(s):
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    if any(k in t for k in _REF):
        return "refinery"
    if any(k in t for k in _GRID):
        return "grid"
    return "city"


def _lead_score(s):
    # НПЗ > энергетика > прочее; confirmed важнее reported (как в build-covers.py)
    cls = {"refinery": 2, "grid": 1, "city": 0}.get(_classify(s), 0)
    conf = 1 if str(s.get("confidence", "")).lower() == "confirmed" else 0
    return (cls, conf)


def pick_top_strike(strikes_path, hours=24):
    """Ведущий удар за последние `hours` для обложки-фолбэка.

    strikes.json — {"strikes": [...]} (или голый список). Даты дневной точности,
    поэтому окно считаем по дате: удар дня D в окне, если D >= (now - hours).date().
    Приоритет: сначала свежее, при равной дате НПЗ>энергетика>прочее и
    confirmed>reported. В возвращённый dict кладём "score" = (cls, conf).
    Возвращает None, если в окне ничего нет.
    """
    import json
    with open(strikes_path, encoding="utf-8") as f:
        data = json.load(f)
    strikes = data["strikes"] if isinstance(data, dict) else data

    cutoff = (datetime.now() - timedelta(hours=hours)).date()
    fresh = []
    for s in strikes:
        try:
            d = datetime.strptime(s["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if d >= cutoff:
            fresh.append((d, s))
    if not fresh:
        return None

    d, lead = max(fresh, key=lambda ds: (ds[0], _lead_score(ds[1])))
    lead = dict(lead)
    lead["score"] = _lead_score(lead)
    return lead

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("usage: caption_cover.py <in.png> <out.png> <city> <event> <date_rus>", file=sys.stderr)
        sys.exit(1)
    caption_cover(*sys.argv[1:6])
    print("wrote", sys.argv[2])
