#!/usr/bin/env python3
"""agents/wave_cover.py — обложка «Волна дронов».

Контракт (зовёт agents/gen-wave.py):
    build_card(event: dict, out_dir: str) -> {"inline_svg": str|None, "png_path": str|None}
    event = {"date","cities","regions","region_list","started_at"}

Порядок (решение Серёги, ТЗ §3):
  1. PRIMARY — фото ЛЕТЯЩИХ ДРОНОВ через существующую NPZ cover-цепочку
     (hermes/scripts/build-covers.py: codex-vps→codex-local), поверх — подпись
     «ВОЛНА ДРОНОВ» + дата через agents/caption_cover.py. Отдаём png_path.
  2. Жёсткий таймаут 5 минут на весь Codex-путь (SIGALRM). Не уложился / упал /
     пусто → фолбэк.
  3. FALLBACK — inline-SVG карточка (дрон + «ВОЛНА ДРОНОВ» + дата + регионы),
     мгновенно, 0 зависимостей. Отдаём inline_svg.

Публикацию обложка НЕ блокирует: SVG-фолбэк гарантирован.
Форс-фолбэк для теста/оффлайна: env NPZ_WAVE_COVER_NOCODEX=1.
OpenRouter — только с NPZ_COVERS_ALLOW_OPENROUTER=1 (последний рубеж, кап-риск).

ponytail: переиспользуем cover-цепочку и caption_cover — не дублируем image-gen;
SVG-фолбэк без geojson-карты (регионы чипами — «над такой-то областью» закрыто),
точная карта — отложенный апгрейд.
"""
import html
import importlib.util
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
CODEX_TIMEOUT_SEC = 300  # «более 5 минут → SVG» (правило Серёги)


def _plural(n, one, few, many):
    n = abs(int(n)); a = n % 10; b = n % 100
    if a == 1 and b != 11:
        return one
    if 2 <= a <= 4 and not (12 <= b <= 14):
        return few
    return many


def _rus(date):
    """'2026-07-12' -> '12 июля 2026'. На кривой вход возвращает вход."""
    try:
        y, m, d = date.split("-")
        return f"{int(d)} {MONTHS[int(m)]} {int(y)}"
    except Exception:
        return str(date)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ───────────────────────── PRIMARY: Codex-фото ─────────────────────────

def _codex_cover(event, out_dir):
    """Фото дронов через cover-цепочку + подпись. None при неудаче/форс-фолбэке."""
    if os.environ.get("NPZ_WAVE_COVER_NOCODEX"):
        return None
    bc_path = ROOT / "hermes" / "scripts" / "build-covers.py"
    if not bc_path.exists():
        return None
    try:
        bc = _load(bc_path, "build_covers")
    except Exception:
        return None

    regions = ", ".join(event.get("region_list", [])[:5]) or "России"
    date_rus = _rus(event.get("date", ""))
    m = {
        "city": "", "event": "ВОЛНА ДРОНОВ", "date_rus": date_rus, "src": "",
        "prompt": (
            f"Дневной документальный новостной фотоснимок: несколько беспилотников "
            f"(дронов) в небе над регионами России ({regions}). Тревожная, но светлая "
            f"дневная атмосфера, фотожурналистика, реализм, широкий план 1200x630 "
            f"горизонталь. БЕЗ текста и букв."
        ),
    }
    try:
        bc.TMP.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    raw = bc.TMP / f"wave-raw-{event.get('date', 'x')}.png"
    try:
        raw.unlink()
    except Exception:
        pass

    order = [b.strip() for b in
             os.environ.get("NPZ_COVER_BACKENDS", "codex-vps,codex-local").split(",")
             if b.strip()]
    ok = False
    for b in order:
        try:
            if b == "codex-vps":
                ok = bc.codex_vps(m, None, raw)
            elif b == "codex-local":
                ok = bc.codex_local(m, None, raw)
            elif b == "openrouter" and os.environ.get("NPZ_COVERS_ALLOW_OPENROUTER"):
                ok = bc.openrouter_gen(m, None, raw)
        except Exception:
            ok = False
        if ok and raw.exists():
            break
    if not (ok and raw.exists()):
        return None

    out = pathlib.Path(out_dir) / f"wave-cover-{event.get('date', 'x')}.png"
    try:  # подпись «ВОЛНА ДРОНОВ» + дата поверх фото
        cc = _load(ROOT / "agents" / "caption_cover.py", "caption_cover")
        cc.caption_cover(str(raw), str(out), "", "ВОЛНА ДРОНОВ", date_rus)
        return str(out) if out.exists() else str(raw)
    except Exception:
        try:
            import shutil
            shutil.copy(str(raw), str(out))
            return str(out)
        except Exception:
            return str(raw)


# ───────────────────────── FALLBACK: inline SVG ─────────────────────────

def _pills(regions, x0, y0, max_w, fs=21, pad=14, gap=9, line_h=40, rows=2):
    """Раскладка регионов чипами слева-направо с переносом. Возвращает (svg, y_end)."""
    out, x, y, used = [], x0, y0, 0
    for name in regions:
        w = int(len(name) * fs * 0.62) + pad * 2   # оценка ширины по символам
        if x + w > x0 + max_w and x > x0:
            x = x0
            y += line_h
            used += 1
            if used >= rows:
                out.append(f'<text x="{x0}" y="{y+fs-4}" font-size="{fs-3}" '
                           f'fill="#ffd9d4" font-family="sans-serif">…ещё '
                           f'{len(regions)-regions.index(name)}</text>')
                break
        out.append(
            f'<g><rect x="{x}" y="{y}" width="{w}" height="{line_h-8}" rx="7" '
            f'fill="rgba(255,255,255,.12)" stroke="rgba(255,255,255,.28)"/>'
            f'<text x="{x+pad}" y="{y+fs+2}" font-size="{fs}" fill="#fff" '
            f'font-family="sans-serif">{html.escape(name)}</text></g>')
        x += w + gap
    return "".join(out), y + line_h


def _drone_icon(cx, cy, s=1.0):
    """Простой квадрокоптер SVG (тело + 4 луча + винты)."""
    def p(v):
        return round(v * s, 1)
    arm = f'stroke="#fff" stroke-width="{p(6)}" stroke-linecap="round"'
    rot = 'fill="none" stroke="#ffd9d4" stroke-width="4"'
    return (
        f'<g transform="translate({cx},{cy})" opacity="0.95">'
        f'<line x1="{-p(46)}" y1="{-p(30)}" x2="{p(46)}" y2="{p(30)}" {arm}/>'
        f'<line x1="{-p(46)}" y1="{p(30)}" x2="{p(46)}" y2="{-p(30)}" {arm}/>'
        f'<circle cx="{-p(46)}" cy="{-p(30)}" r="{p(20)}" {rot}/>'
        f'<circle cx="{p(46)}" cy="{-p(30)}" r="{p(20)}" {rot}/>'
        f'<circle cx="{-p(46)}" cy="{p(30)}" r="{p(20)}" {rot}/>'
        f'<circle cx="{p(46)}" cy="{p(30)}" r="{p(20)}" {rot}/>'
        f'<rect x="{-p(26)}" y="{-p(13)}" width="{p(52)}" height="{p(26)}" rx="{p(8)}" fill="#fff"/>'
        f'<circle cx="0" cy="0" r="{p(6)}" fill="#d23a2e"/>'
        f'</g>')


def _svg_card(event):
    date_rus = _rus(event.get("date", ""))
    n = int(event.get("cities", 0) or 0)
    mreg = int(event.get("regions", len(event.get("region_list", []))) or 0)
    regions = [str(r) for r in event.get("region_list", []) if r]
    pills, y_end = _pills(regions, 70, 400, 1060) if regions else ("", 400)
    return (
        f'<svg viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" role="img" aria-label="Волна дронов {html.escape(date_rus)}">'
        f'<defs><linearGradient id="wbg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#2a0f0c"/><stop offset="1" stop-color="#7a1a12"/>'
        f'</linearGradient></defs>'
        f'<rect width="1200" height="630" fill="url(#wbg)"/>'
        f'<rect width="1200" height="630" fill="none" stroke="#d23a2e" stroke-width="8"/>'
        f'{_drone_icon(1050, 150, 1.15)}'
        f'<text x="70" y="150" font-size="30" fill="#ffb3aa" font-family="sans-serif" '
        f'font-weight="700" letter-spacing="4">🛩 ТОПЛИВНЫЙ ФРОНТ РФ</text>'
        f'<text x="66" y="270" font-size="96" fill="#fff" font-family="sans-serif" '
        f'font-weight="800" letter-spacing="2">ВОЛНА ДРОНОВ</text>'
        f'<text x="70" y="340" font-size="40" fill="#ffd9d4" font-family="sans-serif" '
        f'font-weight="600">{html.escape(date_rus)}</text>'
        f'<text x="70" y="392" font-size="30" fill="#fff" font-family="sans-serif">'
        f'{n} {_plural(n, "город", "города", "городов")} · '
        f'{mreg} {_plural(mreg, "регион", "региона", "регионов")}</text>'
        f'{pills}'
        f'<text x="70" y="600" font-size="20" fill="rgba(255,255,255,.6)" '
        f'font-family="sans-serif">по данным публичного мониторинга radar-map.ru</text>'
        f'</svg>')


# ───────────────────────── контракт ─────────────────────────

def build_card(event, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    # Переиспользуем готовую обложку этой даты (не гонять Codex повторно при
    # регенерации страниц build-nav'ом/текстовыми правками; подпись = дата,
    # для той же даты валидна).
    existing = pathlib.Path(out_dir) / f"wave-cover-{event.get('date', 'x')}.png"
    if existing.exists() and existing.stat().st_size > 1000:
        return {"inline_svg": None, "png_path": str(existing)}
    png = _run_codex_with_timeout(event, out_dir)
    if png:
        return {"inline_svg": None, "png_path": png}
    return {"inline_svg": _svg_card(event), "png_path": None}


def _run_codex_with_timeout(event, out_dir):
    """Codex-путь под жёстким 5-мин SIGALRM. None при таймауте/ошибке/отсутствии signal."""
    try:
        import signal
    except Exception:
        signal = None
    if signal is None or not hasattr(signal, "SIGALRM"):
        try:
            return _codex_cover(event, out_dir)   # без alarm (Windows): полагаемся на внутренние таймауты бэкендов
        except Exception:
            return None

    def _timeout(signum, frame):
        raise TimeoutError("codex cover > 5 min")

    old = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(CODEX_TIMEOUT_SEC)
    try:
        return _codex_cover(event, out_dir)
    except Exception:
        return None
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


if __name__ == "__main__":  # demo/self-check: форс-фолбэк, печать первых 200 символов SVG
    os.environ["NPZ_WAVE_COVER_NOCODEX"] = "1"
    ev = {"date": "2026-07-12", "cities": 49, "regions": 8,
          "region_list": ["Тульская область", "Московская область", "Орловская область",
                          "Калужская область", "Смоленская область", "Краснодарский край"],
          "started_at": "2026-07-12T19:00:00Z"}
    card = build_card(ev, str(ROOT / "assets"))
    assert card["png_path"] is None and card["inline_svg"], "fallback SVG не собран"
    assert "ВОЛНА ДРОНОВ" in card["inline_svg"] and "12 июля 2026" in card["inline_svg"]
    print("OK fallback SVG; first 200 chars:\n" + card["inline_svg"][:200])
