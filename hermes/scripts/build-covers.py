#!/usr/bin/env python3
"""
build-covers.py — обложки новостных сводок «Топливный фронт РФ».

Для каждой даты: берём ЛИД-удар из data/news-archive.json → пытаемся достать РЕАЛЬНОЕ
фото события (og:image из source_url статьи) → генерим по нему обложку через codex
image_gen (img2img по референсу; если реального фото нет — генерим по тексту) → вшиваем
подпись (город + что произошло) через agents/caption_cover.py → assets/cover-<date>.png.

Одна обложка = одна дата, едина для сайта (/news) и Telegram (broadcast.py её же берёт).

Запуск:
  python3 build-covers.py --missing        # только даты без обложки (дефолт)
  python3 build-covers.py --all            # перегенерить все
  python3 build-covers.py --dates 2026-07-05,2026-07-04

PRIMARY-бэкенд: OpenRouter (nano-banana, hermes/gen-cover-openrouter.py) — платный, обходит
обнулённые free-tier квоты. ФОЛБЭК: codex exec image_gen, если у OpenRouter нет ключа/ошибка.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("NPZ_REPO", str(HOME / "npz-tactical-map")))
TMP = HOME / ".hermes" / "covers-tmp"          # codex image_gen sandbox tmp
ARCHIVE = REPO / "data" / "news-archive.json"
ASSETS = REPO / "assets"
CAPTION = REPO / "agents" / "caption_cover.py"
OPENROUTER_SCRIPT = REPO / "hermes" / "gen-cover-openrouter.py"

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
REF = ("нпз", "нефт", "терминал", "переработ", "нефтебаз", "нефтехим", "гпз", "перекачк")
GRID = ("тэц", "тэс", "грэс", "подстанц", "энергет", "электро", "водоснаб")
CITY_LOOK = {
    "Москва": "узнаваемый силуэт Москвы: высотки Москва-Сити и застройка",
    "Санкт-Петербург": "Санкт-Петербург: шпили, Нева, портовые краны",
    "Кстово": "промышленный Кстово с нефтезаводом на окраине",
    "Белгород": "южнорусский Белгород, малоэтажная застройка",
    "Краснодар": "южный Краснодар, зелёные улицы",
    "Уфа": "Уфа с нефтезаводом на реке Белой",
    "Ярославль": "волжский Ярославль с НПЗ ЯНОС",
    "Керчь": "приморская Керчь у пролива",
    "Симферополь": "крымский Симферополь",
    "Севастополь": "приморский Севастополь, бухта",
    "Нижнекамск": "Нижнекамск с нефтехимией ТАНЕКО",
    "Омск": "сибирский Омск с крупным НПЗ",
    "Люберцы": "подмосковные Люберцы, многоэтажки",
}


def rus(d):
    y, m, dd = d.split("-")
    return f"{int(dd)} {MONTHS[int(m)]} {int(y)}"


def look(c):
    return CITY_LOOK.get(c, f"российский город {c}")


def classify(s):
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    if any(k in t for k in REF):
        return "refinery"
    if any(k in t for k in GRID):
        return "grid"
    return "city"


def lead_score(s):
    # ponytail: обложка дня ведёт самым важным ударом — НПЗ > энергетика > прочее,
    # confirmed важнее reported. При равенстве max() берёт первый (порядок брифа).
    cls = {"refinery": 2, "grid": 1, "city": 0}.get(classify(s), 0)
    conf = 1 if str(s.get("confidence", "")).lower() == "confirmed" else 0
    return (cls, conf)


def meta_for(date, brief):
    st = brief.get("strikes", [])
    vo = brief.get("voices", [])
    if st:
        lead = max(st, key=lead_score); city = str(lead.get("city", "")).strip(); kind = classify(lead)
        src = lead.get("source_url", "")
    elif vo:
        city = str(vo[0].get("city", "")).strip(); kind = "queue"; src = vo[0].get("source_url", "")
    else:
        city = "Россия"; kind = "city"; src = ""
    if kind == "refinery":
        event = "удар по НПЗ"; scene = "на дальнем плане столб дыма над нефтезаводом"
    elif kind == "grid":
        event = "удар по энергетике"; scene = "вдалеке дым над подстанцией, часть города без света"
    elif kind == "queue":
        event = "дефицит топлива, очереди"; scene = "длинная очередь машин на заправке"
    else:
        event = "атака дронов"; scene = "в небе следы ПВО и далёкий дым на горизонте"
    prompt = (f"Дневной документальный новостной фотоснимок: {look(city)}. {scene}. "
              f"Светлая ясная атмосфера, дневной свет/золотой час, фотожурналистика, НЕ мрачно и НЕ ночь. "
              f"Реализм, широкий городской план 1200x630 горизонталь. БЕЗ текста и букв.")
    return {"city": city, "event": event, "date_rus": rus(date), "prompt": prompt, "src": src}


def fetch_ref(src_url, out_path):
    """Достаём og:image из статьи-первоисточника и качаем как референс.
    Возвращает путь при успехе + прохождении гейта качества, иначе None."""
    if not src_url:
        return None
    try:
        req = urllib.request.Request(src_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    except Exception:
        return None
    img = None
    for prop in ("og:image", "twitter:image"):
        m = (re.search(r'<meta[^>]+(?:property|name)=["\']' + prop + r'["\'][^>]*content=["\']([^"\']+)', html)
             or re.search(r'content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']' + prop, html))
        if m:
            img = m.group(1); break
    if not img:
        return None
    low = img.lower()
    if any(bad in low for bad in ("logo", "default", "avatar", "placeholder", "sprite", "icon")):
        return None
    try:
        req = urllib.request.Request(img, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=25).read()
        out_path.write_bytes(data)
        from PIL import Image
        im = Image.open(out_path)
        w, h = im.size
        # гейт качества: достаточно крупная, скорее ландшафт, не иконка/квадратик-лого
        if w < 600 or h < 300 or (w / h) < 1.1:
            out_path.unlink(missing_ok=True)
            return None
        return out_path
    except Exception:
        try: out_path.unlink(missing_ok=True)
        except Exception: pass
        return None


def codex_gen(instruction):
    """Запустить codex exec image_gen. True/False по факту создания файла проверяет вызывающий."""
    try:
        subprocess.run(["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", instruction],
                       cwd=str(TMP), timeout=280, capture_output=True, text=True)
    except Exception as e:
        print("  codex error:", e)


def openrouter_gen(m, ref, raw):
    """PRIMARY: сгенерить сырую обложку через OpenRouter (nano-banana). True при успехе (raw записан)."""
    if not OPENROUTER_SCRIPT.exists():
        return False
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        kf = HOME / ".openrouter" / "api_key"
        key = kf.read_text().strip() if kf.exists() else None
    if not key:
        return False
    try:
        spec = importlib.util.spec_from_file_location("gen_cover_openrouter", OPENROUTER_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        prompt = mod.build_prompt(m["city"], m["event"])
        data = mod.openrouter_image(key, prompt, "google/gemini-2.5-flash-image", str(ref) if ref else None)
        raw.write_bytes(data)
        return raw.exists()
    except Exception as e:
        print(f"  openrouter fail: {e}")
        return False


def build_one(date, m):
    raw = TMP / f"raw-{date}.png"
    out = ASSETS / f"cover-{date}.png"
    raw.unlink(missing_ok=True)

    ref = fetch_ref(m["src"], TMP / f"ref-{date}.png")

    mode = "openrouter" + ("+ref" if ref else "")
    if not openrouter_gen(m, ref, raw):
        if ref:
            instr = (f"Use your image_gen tool in EDIT / image-to-image mode. Input reference: {ref} "
                     f"(real photo of the event). Derive a NEW photorealistic 1200x630 horizontal cover that KEEPS "
                     f"the composition and subject (city skyline, smoke, industrial background), bright documentary "
                     f"daylight, our clean style. Remove any watermark/text — NO letters or logos. "
                     f"Save to exactly {raw} then ls -la it.")
            mode = "codex-ref"
        else:
            instr = (f"Use your image_gen tool to generate a photorealistic 1200x630 horizontal image. {m['prompt']} "
                     f"Save to exactly {raw} then ls -la it.")
            mode = "codex-generated"
        codex_gen(instr)
    if ref:
        try: ref.unlink(missing_ok=True)
        except Exception: pass
    if not raw.exists():
        print(f"GENFAIL {date}  ({mode}) — нет картинки (OpenRouter без ключа/ошибка И Codex недоступен)")
        return False
    subprocess.run(["python3", str(CAPTION), str(raw), str(out), m["city"], m["event"], m["date_rus"]],
                   capture_output=True)
    raw.unlink(missing_ok=True)
    if out.exists():
        print(f"OK  {date}  [{mode}]  {m['city']} — {m['event']}")
        return True
    print(f"CAPFAIL {date}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--dates", default="")
    a = ap.parse_args()

    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    briefs = archive.get("briefs", {})
    all_dates = sorted(briefs.keys(), reverse=True)

    if a.dates:
        dates = [d.strip() for d in a.dates.split(",") if d.strip()]
    elif a.all:
        dates = all_dates
    else:  # --missing (дефолт)
        dates = [d for d in all_dates if not (ASSETS / f"cover-{d}.png").exists()]

    if not dates:
        print("build-covers: все обложки на месте, нечего делать.")
        return
    ASSETS.mkdir(exist_ok=True)
    print(f"build-covers: {len(dates)} дат → {dates[0]} … {dates[-1]}")
    ok = 0
    for d in dates:
        if build_one(d, meta_for(d, briefs[d])):
            ok += 1
    print(f"build-covers: готово {ok}/{len(dates)}. Дальше — python3 agents/gen-news.py + publish.")


if __name__ == "__main__":
    main()
