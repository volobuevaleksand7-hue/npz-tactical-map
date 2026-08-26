#!/usr/bin/env python3
"""Generate today's cover using smart city selection from strikes.json.
Uses PIL fallback when image_gen (Codex) is unavailable (429)."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
from caption_cover import pick_top_strike, caption_cover
from PIL import Image, ImageDraw

DOMAIN_RE = re.compile(r"нпз|завод|склад|логист|терминал|нефт|топлив|нефтебаз|резервуар|азс", re.I)


def _cover_caption(target, limit=60):
    """Короткая подпись для обложки из описания цели.

    Из перечисления через запятую берём первую часть по профилю проекта (топливо и
    логистика); если такой нет — первую вообще. Режем по границе слова, а не по букве.
    """
    parts = [x.strip() for x in str(target).split(",") if x.strip()]
    if not parts:
        return ""
    pick = next((x for x in parts if DOMAIN_RE.search(x)), parts[0])
    if len(pick) <= limit:
        return pick
    return pick[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—") + "\u2026"


def demo():
    assert _cover_caption("частный детский центр, жилые многоквартирные дома, "
                          "логистический центр Ozon") == "логистический центр Ozon"
    assert _cover_caption("НПЗ Лукойл") == "НПЗ Лукойл"
    assert _cover_caption("") == ""
    long_ = _cover_caption("склад " + "очень " * 40)
    assert len(long_) <= 61 and long_.endswith("\u2026") and " " in long_, long_
    assert not long_.rstrip("\u2026").endswith(" "), long_
    # очень длинный город + очень длинная подпись не выходят за пределы холста
    # (23.08.2026: «НОВОКУЙБЫШЕВСК» и вторая строка обрезало по обоим краям —
    # реальный прогон рендера через caption_cover, не только текстовая логика)
    from caption_cover import _selfcheck as _cc_selfcheck
    _cc_selfcheck()
    print("gen_cover_today demo OK")


W, H = 1200, 630
BG = (14, 19, 28)
AMBER = (255, 180, 67)


def _make_dark_bg():
    """Create a dark background with industrial glow effects."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Industrial glow — upper right (fire)
    for r in range(300, 0, -3):
        intensity = (300 - r) / 300.0
        color = (
            min(255, int(15 + 90 * intensity)),
            min(255, int(20 + 35 * intensity)),
            min(255, int(35 + 15 * intensity)),
        )
        d.ellipse([900 - r, 150 - r, 900 + r, 150 + r], fill=color)

    # Industrial glow — lower left (dimmer)
    for r in range(200, 0, -3):
        intensity = (200 - r) / 200.0 * 0.4
        color = (
            min(255, int(15 + 50 * intensity)),
            min(255, int(20 + 20 * intensity)),
            min(255, int(35 + 25 * intensity)),
        )
        d.ellipse([300 - r, 400 - r, 300 + r, 400 + r], fill=color)

    # Industrial towers
    towers = [
        (850, 100, 18, 200), (890, 120, 14, 180), (930, 80, 20, 220),
        (780, 140, 12, 160), (960, 110, 16, 190),
        (1020, 150, 10, 140), (810, 130, 14, 170),
    ]
    for bx, by, bw, bh in towers:
        d.rectangle([bx, by, bx + bw, by + bh], fill=(25, 30, 45))
        d.line([(bx, by), (bx, by + bh)], fill=(35, 40, 55), width=1)
        d.rectangle([bx - 2, by - 12, bx + bw + 2, by + 2], fill=(180, 80, 20))
        d.rectangle([bx + 2, by - 18, bx + bw - 2, by - 10], fill=(220, 120, 30))
        d.rectangle([bx + 4, by - 22, bx + bw - 4, by - 16], fill=(255, 160, 40))

    # Piping
    for ly in [290, 310]:
        d.line([(780, ly), (1050, ly)], fill=(30, 35, 48), width=2)
    d.line([(820, 290), (820, 310)], fill=(30, 35, 48), width=2)
    d.line([(950, 290), (950, 310)], fill=(30, 35, 48), width=2)

    # Horizontal rules
    for ly in [180, 420]:
        d.line([(48, ly), (W - 48, ly)], fill=(30, 35, 50), width=1)

    return img


def generate_cover_auto(day=None):
    """Обложка по ведущему удару. day=YYYY-MM-DD — добор за прошедший день.

    🔴 Расширить окно pick_top_strike для добора НЕДОСТАТОЧНО: она возвращает
    ведущий удар за весь период, поэтому за 25.08 рисовалась картинка по удару
    26-го — поймано на живом доборе, обе обложки вышли байт в байт одинаковыми.
    Отбираем удары РОВНО этих суток во временный файл и отдаём их той же функции:
    приоритет (НПЗ > энергетика > прочее, confirmed > reported) не дублируем.
    """
    strikes_path = os.path.join(os.path.dirname(__file__), "..", "data", "strikes.json")
    if day:
        import json as _json, tempfile
        with open(strikes_path, encoding="utf-8") as _fh:
            _doc = _json.load(_fh)
        _all = _doc if isinstance(_doc, list) else _doc.get("strikes", [])
        _day_only = [x for x in _all if str(x.get("date", ""))[:10] == day]
        if not _day_only:
            print("ERROR: за %s в архиве нет ударов" % day)
            sys.exit(1)
        _tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                           encoding="utf-8")
        _json.dump({"strikes": _day_only}, _tmp, ensure_ascii=False)
        _tmp.close()
        strike = pick_top_strike(_tmp.name, hours=24 * 3650)
        os.unlink(_tmp.name)
    else:
        strike = pick_top_strike(strikes_path, hours=24)

    if not strike:
        print("ERROR: No strikes found in last 24h")
        sys.exit(1)

    city = strike["city"]
    # Подпись на обложке — не сырой target. 24.08 удар по Краснодару описан как
    # «частный детский центр, жилые многоквартирные дома, логистический центр Ozon»,
    # и слепая обрезка по 57 символам дала на промо-картинке «частный детский центр,
    # жилые многоквартирные дома, логист...» — оборвано на полуслове и мрачно.
    # Берём часть перечисления по профилю проекта (топливо и логистика), режем по слову.
    event = _cover_caption(strike["target"])
    date_str = strike["date"]  # "2026-07-06"

    # Format date for display
    from datetime import datetime
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    # 🔴 Было {6: "июня", 7: "июля"} — остальные месяцы падали в str(dt.month), и с
    # 1 августа обложки уходили с датой «24 8 2026» вместо «24 августа 2026».
    months = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
              7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября",
              12: "декабря"}
    date_rus = f"{dt.day} {months.get(dt.month, str(dt.month))} {dt.year}"

    print(f"Selected: {city} | {event} | {date_rus}")
    print(f"Confidence: {strike['confidence']}, Score: {strike['score']}")

    # Generate dark background
    bg_path = "/tmp/cover_bg.png"
    bg = _make_dark_bg()
    bg.save(bg_path, "PNG")

    # Apply caption overlay
    # Always save as today's date for the cover filename
    today = day or datetime.now().strftime("%Y-%m-%d")
    # 🔴 было захардкожено "/root/npz-tactical-map/..." — работало только на VPS,
    # локальный прогон (Mac/worktree) падал бы на несуществующем /root. Путь теперь
    # считаем от расположения самого скрипта (agents/.. = корень репо), как strikes_path выше.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(repo_root, "assets", f"cover-{today}.png")
    caption_cover(bg_path, out_path, city, event, date_rus)

    # Cleanup
    os.remove(bg_path)
    print(f"wrote {out_path}")
    return out_path


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
        sys.exit(0)

    _day = None
    if "--date" in sys.argv:
        _day = sys.argv[sys.argv.index("--date") + 1]
    generate_cover_auto(_day)

