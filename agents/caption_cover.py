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
import os as _os
import importlib.util as _ilu
import platform as _plat
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
CREAM = (243, 246, 248)    # заголовок — site --ink (dark theme), чуть светлее для контраста
DIM = (163, 181, 193)      # подпись-событие — site --ink-dim (dark theme)
AMBER = (255, 180, 67)     # site --amber (dark theme #ffb443)
INK_ON_AMBER = (36, 21, 0)  # site --amber на амбере (#241500, как .mode-pill)

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

if _plat.system() == "Darwin":
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
else:
    # Linux VPS — Liberation Sans (metrically compatible with Arial)
    FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# ponytail: город/событие/дата — переменный текст, который свободно смешивает кириллицу,
# латиницу (LUKOIL, Ozon, Wildberries) и цифры (даты, «500 кВ»). Проектные assets/fonts/*.woff2
# нарезаны по unicode-range ИСКЛЮЧИТЕЛЬНО для <link> в браузере — один файл держит либо
# кириллицу, либо латиницу+цифры+пунктуацию, никогда оба разом (проверено fontTools: у
# rubik-800-u-0301.woff2 нет ни одной цифры и половины латиницы). Единственный шрифт с
# полным покрытием на диске — системный Arial/Liberation, поэтому весь динамический текст
# рисуем им. Кикер-бейдж — фиксированная чисто кириллическая строка без цифр, для неё
# безопасно и уместно взять проектный JetBrains Mono (совпадает с .mode-pill на сайте).
KICKER_FONT = _os.path.join(_REPO, "assets", "fonts", "jetbrains-mono-600-u-0301.woff2")


def _safe_font(path, size, fallback=FONT_BOLD):
    """Честный фолбэк: файл отсутствует/не грузится → системный шрифт."""
    for p in (path, fallback):
        if p and _os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_w):
    """Жадный перенос по словам, каждая строка гарантированно ≤ max_w.

    Одно слово шире max_w (длинный урбоним без пробелов) режем по буквам —
    это и есть страховка от обрезки за края холста из 23.08.2026.
    """
    lines = []
    cur = ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        if draw.textlength(word, font=font) <= max_w:
            cur = word
            continue
        # слово само шире max_w — режем по буквам. Оставляем "…", иначе строка
        # выглядит как полное название, хотя часть символов молча выброшена.
        trimmed = word
        while len(trimmed) > 1 and draw.textlength(trimmed + "…", font=font) > max_w:
            trimmed = trimmed[:-1]
        cur = trimmed + "…"
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit_wrapped(draw, text, font_path, max_w, start, min_size, max_lines):
    """Подбирает размер шрифта (start→min_size) так, чтобы перенос уместился в
    max_lines строк. Если и на min_size строк больше — обрезаем последнюю
    строку многоточием. Возвращает (font, [строки]); каждая строка ≤ max_w."""
    size = start
    font = lines = None
    while size >= min_size:
        font = _safe_font(font_path, size)
        lines = _wrap_text(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
        size -= 2
    keep = lines[:max_lines]
    last = keep[-1]
    while len(last) > 1 and draw.textlength(last + "…", font=font) > max_w:
        last = last[:-1]
    keep[-1] = last.rstrip(" ,;:-—") + "…"
    return font, keep


def caption_cover(in_path, out_path, city, event, date_rus):
    img = Image.open(in_path).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)

    # нижняя градиентная подложка для читаемости подписи (тёмно-синий в тон борду сайта,
    # не зелёный — прежний (4,20,11) спорил по оттенку с навигационным фоном обложки)
    scrim = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, (y - H * 0.46) / (H * 0.54))
        scrim.putpixel((0, y), int(225 * (t ** 1.5)))
    scrim = scrim.resize((W, H))
    black = Image.new("RGB", (W, H), (7, 11, 18))
    img = Image.composite(black, img, scrim)

    d = ImageDraw.Draw(img)
    pad = 56
    max_w = W - pad * 2

    # верхний бейдж-«кикер» — сплошная амбер-плашка, как .mode-pill на сайте
    kicker = "ТОПЛИВНЫЙ ФРОНТ РФ"
    fk = _safe_font(KICKER_FONT, 24, fallback=FONT_BOLD)
    kw = d.textlength(kicker, font=fk)
    chip_pad_x, chip_pad_y = 16, 10
    chip = [pad - chip_pad_x, pad - chip_pad_y, pad + kw + chip_pad_x, pad + 26 + chip_pad_y]
    d.rounded_rectangle(chip, radius=8, fill=AMBER)
    d.text((pad, pad), kicker, font=fk, fill=INK_ON_AMBER)

    # блоки снизу вверх: дата → событие (до 2 строк) → город (до 2 строк).
    # Каждый блок независимо перенесён и ужат под max_w — ничего не выходит за холст.
    blocks = []  # (lines, font, color, leading)
    if city:
        cfont, clines = _fit_wrapped(d, city, FONT_BOLD, max_w, 78, 42, 2)
        blocks.append((clines, cfont, CREAM, 1.06))
    if event:
        efont, elines = _fit_wrapped(d, event, FONT_REG, max_w, 36, 23, 2)
        blocks.append((elines, efont, DIM, 1.18))
    dfont, dlines = _fit_wrapped(d, "● " + date_rus, FONT_BOLD, max_w, 27, 20, 1)
    blocks.append((dlines, dfont, AMBER, 1.1))

    BLOCK_GAP = 16
    rows = []  # (text, font, color, height)
    for i, (lines, font, color, leading) in enumerate(blocks):
        asc, desc = font.getmetrics()
        line_h = int((asc + desc) * leading)
        for j, ln in enumerate(lines):
            rows.append((ln, font, color, line_h, BLOCK_GAP if (j == 0 and i > 0) else 0))

    total_h = sum(h + g for _, _, _, h, g in rows)
    y = H - pad - total_h
    for text, font, color, line_h, gap in rows:
        y += gap
        d.text((pad, y), text, font=font, fill=color)
        y += line_h

    img.save(out_path, "PNG")
    # сжать сразу при генерации (иначе 2 МБ PNG жрут Fast Data Transfer на Vercel)
    try:
        # _os, а не os: голого `import os` в модуле нет (ниже — `import os as _os`),
        # поэтому хук молча падал в NameError на КАЖДОЙ обложке и сжатие не работало.
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from optimize_covers import optimize_cover
        optimize_cover(out_path)
    except Exception as _e:
        print("optimize_covers hook skip:", _e)
    return out_path


# --- lead strike selection (PIL-fallback cover) ---------------------------
# Классификация — из общего agents/strike_class.py. Раньше здесь лежала копия
# констант с припиской «синхронизируй второй список»: не сработало — 15.07 в
# build-covers добавили класс sea, сюда не перенесли, и фолбэк подписывал удар
# по танкерам как «удар по НПЗ». Один список на оба пути.
from datetime import datetime, timedelta

_sc_spec = _ilu.spec_from_file_location(
    "strike_class", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "strike_class.py"))
_sc = _ilu.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(_sc)
_classify, _lead_score = _sc.classify, _sc.lead_score


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


def _selfcheck():
    """assert-демо: перенос/ужатие держит КАЖДУЮ строку в пределах холста —
    и на «нормальном» тексте, и на экстремально длинном городе+подписи."""
    from PIL import Image as _Image
    im = _Image.new("RGB", (W, H))
    dr = ImageDraw.Draw(im)
    pad = 56
    max_w = W - pad * 2

    cases = [
        ("Кстово", "НПЗ LUKOIL-Nizhegorodnefteorgsintez"),
        ("Красноярский район", "Астраханский газоперерабатывающий завод (ГПЗ)"),
        ("Оченьдлинноеслитноеназваниенаселённогопунктабезединогопробелавстроке",
         "Очень длинная составная подпись про нефтеперерабатывающий завод и логистический терминал в области, которая ни за что не должна вылезти за пределы обложки"),
    ]
    for city, event in cases:
        cfont, clines = _fit_wrapped(dr, city, FONT_BOLD, max_w, 78, 42, 2)
        for ln in clines:
            assert dr.textlength(ln, font=cfont) <= max_w + 1, (city, ln)
        efont, elines = _fit_wrapped(dr, event, FONT_REG, max_w, 36, 23, 2)
        for ln in elines:
            assert dr.textlength(ln, font=efont) <= max_w + 1, (event, ln)
        assert len(clines) <= 2 and len(elines) <= 2
    print("caption_cover selfcheck OK (%d cases, none overflow %dpx)" % (len(cases), max_w))


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
        sys.exit(0)
    if len(sys.argv) != 6:
        print("usage: caption_cover.py <in.png> <out.png> <city> <event> <date_rus>", file=sys.stderr)
        sys.exit(1)
    caption_cover(*sys.argv[1:6])
    print("wrote", sys.argv[2])
