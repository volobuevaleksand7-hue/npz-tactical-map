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

Цепочка бэкендов (env NPZ_COVER_BACKENDS, дефолт "codex-vps,codex-local,openrouter"):
  1. codex-vps   — Codex на VPS (всегда включён). На самом VPS = локальный codex; с Мака —
                   codex по ssh на VPS + картинку тащим обратно (env NPZ_VPS_SSH, деф. hermes-vps).
  2. codex-local — Codex на этой машине (на Маке — Mac-Codex).
  3. openrouter  — платный nano-banana (~$0.04/шт), последний рубеж. Ключ capped $10 → без
                   денег просто 403 (в 2026-07 весь $10-лимит утёк именно на эти обложки).
Отключить платный OpenRouter: NPZ_COVER_BACKENDS="codex-vps,codex-local".
"""
import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
REPO = Path(os.environ.get("NPZ_REPO", str(HOME / "npz-tactical-map")))
TMP = HOME / ".hermes" / "covers-tmp"          # codex image_gen sandbox tmp
ARCHIVE = REPO / "data" / "news-archive.json"
STRIKES = REPO / "data" / "strikes.json"
ASSETS = REPO / "assets"
CAPTION = REPO / "agents" / "caption_cover.py"
OPENROUTER_SCRIPT = REPO / "hermes" / "gen-cover-openrouter.py"

# Порядок бэкендов обложки: Codex@VPS → Codex@локально(Mac) → OpenRouter (правило владельца).
# codex-vps: сами на VPS → локальный codex; на Маке → codex по ssh на VPS + картинка обратно.
IS_VPS = str(REPO).startswith("/root")
VPS_SSH = os.environ.get("NPZ_VPS_SSH", "hermes-vps")
VPS_TMP = "/root/.hermes/covers-tmp"
DEFAULT_BACKENDS = "codex-vps,codex-local,openrouter"

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
# Классификация удара — единый источник agents/strike_class.py (см. его docstring:
# копий было две, разъехались за два дня и PIL-фолбэк подписывал море как «удар по НПЗ»).
_sc_spec = importlib.util.spec_from_file_location("strike_class", str(REPO / "agents" / "strike_class.py"))
_sc = importlib.util.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(_sc)
classify, lead_score, EVENT_LABEL = _sc.classify, _sc.lead_score, _sc.EVENT_LABEL
CITY_LOOK = {
    "Чёрное море (акватория)": "открытая акватория Чёрного моря, морской горизонт, вдали силуэты судов",
    "Азовское море (акватория)": "открытая акватория Азовского моря, морской горизонт, вдали силуэты судов",
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


def lead_from_archive(date):
    """Лид-удар за дату из полного архива data/strikes.json.

    Зачем: бриф может быть ещё ПУСТ на момент сборки обложки. Доказанная гонка
    (16.07): watchdog самолечил сводку в 05:16 UTC, а сборщик долил удары в
    07:01 — обложка успела собраться по пустому брифу и навсегда осталась
    генерической («Россия / атака дронов»), потому что --missing не пересобирает
    уже существующий файл. strikes.json к тому моменту удары обычно уже содержит.
    """
    try:
        data = json.loads(STRIKES.read_text(encoding="utf-8"))
    except Exception:
        return None
    ss = data["strikes"] if isinstance(data, dict) else data
    day = [s for s in ss if str(s.get("date", "")).strip() == date]
    return max(day, key=lead_score) if day else None


def meta_for(date, brief):
    """Мета обложки. None = лида нет → обложку НЕ выдумываем (см. main)."""
    st = brief.get("strikes", [])
    vo = brief.get("voices", [])
    lead = max(st, key=lead_score) if st else lead_from_archive(date)
    if lead:
        city = str(lead.get("city", "")).strip(); kind = classify(lead)
        src = lead.get("source_url", "")
    elif vo:
        city = str(vo[0].get("city", "")).strip(); kind = "queue"; src = vo[0].get("source_url", "")
    else:
        # ponytail: раньше тут было city="Россия"; kind="city" → обложка «Россия /
        # атака дронов». Это враньё в проде: подпись обещает конкретный объект,
        # которого нет, и на день без данных мы утверждали атаку. Лучше не собрать
        # обложку вовсе — watchdog увидит её отсутствие и пересоберёт позже,
        # когда удары приедут.
        return None
    if not city:
        return None
    if kind == "sea":
        scene = "открытое море, на горизонте горящий танкер, столб дыма над водой"
    elif kind == "refinery":
        scene = "на дальнем плане столб дыма над нефтезаводом"
    elif kind == "grid":
        scene = "вдалеке дым над подстанцией, часть города без света"
    elif kind == "queue":
        scene = "длинная очередь машин на заправке"
    else:
        scene = "в небе следы ПВО и далёкий дым на горизонте"
    event = "дефицит топлива, очереди" if kind == "queue" else EVENT_LABEL[kind]
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


def _codex_instr(raw_path, ref_path, m):
    """Инструкция codex image_gen под заданный путь вывода (локальный или удалённый)."""
    if ref_path:
        return (f"Use your image_gen tool in EDIT / image-to-image mode. Input reference: {ref_path} "
                f"(real photo of the event). Derive a NEW photorealistic 1200x630 horizontal cover that KEEPS "
                f"the composition and subject (city skyline, smoke, industrial background), bright documentary "
                f"daylight, our clean style. Remove any watermark/text — NO letters or logos. "
                f"Save to exactly {raw_path} then ls -la it.")
    return (f"Use your image_gen tool to generate a photorealistic 1200x630 horizontal image. {m['prompt']} "
            f"Save to exactly {raw_path} then ls -la it.")


def codex_local(m, ref, raw):
    """Codex на ЭТОЙ машине (на VPS = VPS-Codex, на Маке = Mac-Codex). True если raw записан."""
    instr = _codex_instr(str(raw), str(ref) if ref else None, m)
    try:
        subprocess.run(["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", instr],
                       cwd=str(TMP), timeout=280, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001
        print("  codex-local error:", e)
    return raw.exists()


def codex_vps(m, ref, raw):
    """Codex на VPS. На самом VPS = локальный codex; с Мака — по ssh на VPS + забрать картинку."""
    if IS_VPS:
        return codex_local(m, ref, raw)
    date = raw.stem.replace("raw-", "")
    r_raw = f"{VPS_TMP}/raw-{date}.png"
    r_ref = f"{VPS_TMP}/ref-{date}.png" if ref else None
    ssh_o = ["-o", "ConnectTimeout=15"]
    try:
        subprocess.run(["ssh", *ssh_o, VPS_SSH, f"mkdir -p {VPS_TMP}; rm -f {r_raw}"],
                       timeout=25, capture_output=True)
        if ref and subprocess.run(["scp", "-q", *ssh_o, str(ref), f"{VPS_SSH}:{r_ref}"],
                                  timeout=60).returncode != 0:
            r_ref = None  # референс не доехал — сгенерим без него
        instr = _codex_instr(r_raw, r_ref, m)
        cmd = f"cd {VPS_TMP} && codex exec --dangerously-bypass-approvals-and-sandbox {shlex.quote(instr)}"
        subprocess.run(["ssh", *ssh_o, VPS_SSH, cmd], timeout=300, capture_output=True, text=True)
        subprocess.run(["scp", "-q", *ssh_o, f"{VPS_SSH}:{r_raw}", str(raw)], timeout=60, capture_output=True)
    except Exception as e:  # noqa: BLE001
        print(f"  codex-vps fail: {e}")
    return raw.exists()


def openrouter_gen(m, ref, raw):
    """FALLBACK (платный, opt-in): сгенерить обложку через OpenRouter (nano-banana). True при успехе."""
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

    ref = None if m.get("no_ref") else fetch_ref(m["src"], TMP / f"ref-{date}.png")

    # Цепочка бэкендов по порядку (дефолт: codex-vps → codex-local → openrouter).
    order = [b.strip() for b in os.environ.get("NPZ_COVER_BACKENDS", DEFAULT_BACKENDS).split(",") if b.strip()]
    mode = ""
    for be in order:
        if be == "codex-vps" and codex_vps(m, ref, raw):
            mode = "codex@vps" + ("(local)" if IS_VPS else "(ssh)"); break
        if be == "codex-local" and codex_local(m, ref, raw):
            mode = "codex@vps" if IS_VPS else "codex@mac"; break
        if be == "openrouter" and openrouter_gen(m, ref, raw):  # платный; ключ capped $10 → сам 403
            mode = "openrouter"; break

    if ref:
        try: ref.unlink(missing_ok=True)
        except Exception: pass
    if not raw.exists():
        print(f"GENFAIL {date} — ни один бэкенд ({'→'.join(order)}) не дал картинку")
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
    ap.add_argument("--no-ref", action="store_true", help="не тащить og:image статьи как референс (когда он не по делу)")
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
    ok = skipped = 0
    for d in dates:
        meta = meta_for(d, briefs[d])
        if meta is None:
            skipped += 1
            print(f"SKIP {d} — лид-удара нет ни в брифе, ни в strikes.json; генерическую "
                  f"обложку не выдумываем, соберётся следующим прогоном")
            continue
        meta["no_ref"] = a.no_ref
        if build_one(d, meta):
            ok += 1
    tail = f", пропущено {skipped}" if skipped else ""
    print(f"build-covers: готово {ok}/{len(dates)}{tail}. Дальше — python3 agents/gen-news.py + publish.")


if __name__ == "__main__":
    main()
