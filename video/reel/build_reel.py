#!/usr/bin/env python3
"""Рилс «Топливный фронт РФ»: карта сайта -> наезд на удар -> табличка -> кадры очевидцев.

  python3 video/reel/build_reel.py select  <YYYY-MM-DD>              # какие удары попадут в ролик
  python3 video/reel/build_reel.py prepare <YYYY-MM-DD> <build_dir>  # клипы + скриншот карты + targets
  python3 video/reel/build_reel.py compose <YYYY-MM-DD> <build_dir>  # index.html + plan.json + описание
  (звук — общий mix из video/build.py: `python3 video/build.py mix <build_dir> silent.mp4 out.mp4`)

Отдельно от ежедневного ролика (video/build.py + video/template/): тот не меняется.
Данные — data/strikes.json (тот же файл, что рисует карта сайта), чистка — normalize_strike
из agents/gen-news.py (нейтральность, украинизмы). Мощности/координаты НПЗ — fuel-state.json.
"""
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REEL = Path(__file__).resolve().parent
VIDEO = REEL.parent
ROOT = VIDEO.parent
TPL = REEL / "template"
SITE_HOST = "npz-tactical-map.vercel.app"
TG_HANDLE = "@npz_karta_online"
MAX_STRIKES = 3


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("daily_build", VIDEO / "build.py")   # общие функции ежедневного ролика (mix, matchers)
G = B.G                                          # agents/gen-news.py
esc = lambda s: html.escape(str(s), quote=True)

INFRA_KW = G.REFINERY_KW + ("лпдс", "нпс", "азс", "нефтепровод", "трубопровод", "резервуар")
INDUSTRY_KW = ("промышл", "завод", "предприят", "склад")


def strike_class(s):
    """2 — топливо/энергетика (кадры ищем), 1 — промышленность (кадры ищем), 0 — прочее (только табличка)."""
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    if any(k in t for k in INFRA_KW):
        return 2
    if any(k in t for k in INDUSTRY_KW):
        return 1
    return 0


def _f(v):
    try:
        v = float(v)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def locate(s, refineries, all_strikes):
    """lat/lon удара; пустые — по совпавшему НПЗ из fuel-state, затем по тому же городу в архиве."""
    lat, lon = _f(s.get("lat")), _f(s.get("lon"))
    if lat and lon:
        return lat, lon
    text = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    for rx, r in B.refinery_matchers(refineries):
        if rx.search(text) and _f(r.get("lat")):
            return float(r["lat"]), float(r["lon"])
    city = str(s.get("city") or "").strip()
    for o in all_strikes:
        if city and str(o.get("city") or "").strip() == city and _f(o.get("lat")) and _f(o.get("lon")):
            return float(o["lat"]), float(o["lon"])
    return None


def load_day(date):
    data = json.loads((ROOT / "data" / "strikes.json").read_text(encoding="utf-8"))
    arr = data.get("strikes", data) if isinstance(data, dict) else data
    fuel = json.loads((ROOT / "data" / "fuel-state.json").read_text(encoding="utf-8"))
    refs = fuel.get("refineries", [])
    day = []
    for raw in arr:
        if str(raw.get("date", ""))[:10] != date:
            continue
        s = G.normalize_strike(raw)
        ll = locate(s, refs, arr)
        if ll:
            s["lat"], s["lon"] = ll
        else:
            s["lat"] = s["lon"] = None
        s["cls"] = strike_class(s)
        day.append(s)
    return day, refs


def select_strikes(date):
    """(выбранные до 3, все удары дня). Топливо/энергетика -> промышленность -> прочее,
    внутри — strike_rank gen-news (класс цели, confirmed). Один город — один раз.
    Слухи (rumored) не показываем."""
    day, _ = load_day(date)
    pool = [s for s in day if s["lat"] is not None
            and str(s.get("confidence", "reported")).lower() in ("confirmed", "reported")]
    pool.sort(key=lambda s: (s["cls"], G.strike_rank(s)), reverse=True)
    out, cities = [], set()
    for s in pool:
        c = str(s.get("city") or s.get("region") or "").strip().lower()
        if c in cities:
            continue
        cities.add(c)
        out.append(s)
        if len(out) >= MAX_STRIKES:
            break
    return out, day


# ───────────────────────────── тексты ─────────────────────────────

def object_name(s, refs):
    text = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    for rx, r in B.refinery_matchers(refs):
        if rx.search(text):
            return r["name"]
    t = str(s.get("target") or "").strip()
    t = re.sub(r"\s*\((?:линейная[^)]*)\)", "", t, flags=re.I)  # «ЛПДС (линейная …) «Самара»» -> «ЛПДС «Самара»»
    t = re.split(r",|;|\s+[—–]\s+", t)[0].strip()
    t = re.sub(r"нефтеперерабатывающий завод", "НПЗ", t, flags=re.I)
    t = t[:1].upper() + t[1:]
    return t if len(t) <= 46 else t[:44].rstrip() + "…"


def what_happened(s):
    d = re.sub(r"\s+", " ", str(s.get("detail") or "")).strip()
    if not d:
        return f"Сообщается об атаке БПЛА. Объект: {object_name(s, [])}."
    # не резать на сокращениях «г.», «обл.», «р-н.», «ул.», «с.», «пос.» и инициалах
    first = re.split(r"(?<!\bг\.)(?<!\bс\.)(?<!обл\.)(?<!р-н\.)(?<!ул\.)(?<!пос\.)(?<=[.!?])\s+(?=[А-ЯЁA-Z«\"])", d)
    out = first[0]
    if len(out) < 60 and len(first) > 1:
        out += " " + first[1]
    return out if len(out) <= 120 else out[:118].rsplit(" ", 1)[0] + "…"


def kind_label(s):
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    for keys, label in ((("нпз", "нефтеперераб"), "НПЗ"), (("лпдс", "нпс", "перекачк", "трубопровод", "нефтепровод"), "нефтепровод"),
                        (("нефтебаз", "резервуар", "хранилищ"), "нефтебаза"), (("терминал", "порт"), "терминал"),
                        (("подстанц", "тэц", "тэс", "грэс", "энерг"), "энергетика"),
                        (("промышл", "завод", "предприят"), "промышленность")):
        if any(k in t for k in keys):
            return label
    return "объект"


def dative_object(name):
    """«Волгоградский НПЗ» -> «Волгоградскому НПЗ»; «ЛПДС «Самара»» -> без изменений."""
    w = name.split(" ", 1)
    first = w[0]
    for a, b in (("ский", "скому"), ("ный", "ному"), ("кий", "кому"), ("ой", "ому")):
        if first.endswith(a):
            first = first[: -len(a)] + b
            break
    return first + (" " + w[1] if len(w) > 1 else "")


def fire_score(path):
    """Яркость + доля тёплых насыщенных пикселей (огонь/дым на свету) — для фона постера."""
    from PIL import Image
    im = Image.open(path).convert("RGB").resize((90, 160))
    px = list(im.getdata())
    lum = sum(0.3 * r + 0.59 * g + 0.11 * b for r, g, b in px) / len(px)
    warm = sum(1 for r, g, b in px if r > 150 and r > g * 1.3 and r > b * 1.6) / len(px)
    return lum * 0.4 + warm * 300


def poster_head(sel, day, refs):
    lead = sel[0] if sel and sel[0]["cls"] == 2 else None
    n = len(day)
    if lead:
        return "УДАР ПО " + dative_object(object_name(lead, refs)).upper()
    return f"{n} {G.plural(n, 'УДАР', 'УДАРА', 'УДАРОВ')} ПО РФ"


# ───────────────────────────── prepare ─────────────────────────────

def map_bounds(points):
    lats = [p[0] for p in points] or [55.0]
    lons = [p[1] for p in points] or [40.0]
    lo_lat, hi_lat = min(lats) - 2.5, max(lats) + 2.5
    lo_lon, hi_lon = min(lons) - 2.5, max(lons) + 2.5
    # не уже 18° по долготе: карта должна читаться как карта сайта, а не как один город
    if hi_lon - lo_lon < 18:
        c = (hi_lon + lo_lon) / 2
        lo_lon, hi_lon = c - 9, c + 9
    return [[lo_lat, lo_lon], [hi_lat, hi_lon]]


def prepare(date, build: Path):
    sys.path.insert(0, str(REEL))
    import fetch_clips as FC
    sel, day = select_strikes(date)
    if not sel:
        sys.exit(f"build_reel: за {date} нет ударов с координатами — рилс не собирается")
    build.mkdir(parents=True, exist_ok=True)
    (build / "assets").mkdir(exist_ok=True)
    clips = []
    for s in sel:
        c = FC.fetch_for(s, build / "assets") if s["cls"] >= 1 else None
        clips.append(c)
    pts = [{"id": f"s{i}", "lat": s["lat"], "lon": s["lon"]} for i, s in enumerate(sel)]
    pts += [{"id": f"d{i}", "lat": s["lat"], "lon": s["lon"]} for i, s in enumerate(day) if s["lat"] is not None]
    targets = {"bounds": map_bounds([(p["lat"], p["lon"]) for p in pts]), "points": pts,
               "url": f"https://{SITE_HOST}/"}
    (build / "targets.json").write_text(json.dumps(targets), encoding="utf-8")
    subprocess.run(["node", str(REEL / "capture_map.mjs"), str(build / "targets.json"),
                    str(build / "assets" / "map.jpg"), str(build / "map-points.json")],
                   check=True, timeout=240, cwd=str(VIDEO))
    (build / "clips.json").write_text(json.dumps(clips, ensure_ascii=False), encoding="utf-8")
    print(json.dumps([{"city": s.get("city"), "clip": c} for s, c in zip(sel, clips)], ensure_ascii=False))


# ───────────────────────────── compose ─────────────────────────────

POSTER = 1.3     # постер-обложка (первый кадр в ленте Shorts)
OVER = 1.1       # общий план карты
FLY = 1.6        # перелёт к удару
SIGN = 1.6       # табличка висит
SIGN_ONLY = 2.3  # табличка без кадров
DIVE = 0.55      # «влёт» в табличку
OUTRO = 5.0      # финальная карточка
S0 = 1080 / 3240   # масштаб общего плана (вся ширина скриншота)
SZ = 1.15          # масштаб у удара


def compose(date, build: Path):
    sel, day = select_strikes(date)
    _, refs = load_day(date)
    clips = json.loads((build / "clips.json").read_text(encoding="utf-8"))
    mp = json.loads((build / "map-points.json").read_text(encoding="utf-8"))
    P = {p["id"]: p for p in mp["points"]}
    IW, IH = mp["w"], mp["h"]

    for f in ("fonts",):
        shutil.copytree(VIDEO / "template" / "assets" / f, build / "assets" / f, dirs_exist_ok=True)
    shutil.copy2(VIDEO / "node_modules" / "gsap" / "dist" / "gsap.min.js", build / "assets" / "gsap.min.js")

    # камера: ключевые кадры (t, x, y, s) в пикселях скриншота; dip — «подъём» камеры на перелёте
    cx0, cy0 = IW / 2, IH / 2
    cam = [{"t": 0, "x": cx0, "y": cy0, "s": S0 * 1.25, "dip": 0}]
    t = POSTER
    cam.append({"t": t + OVER, "x": cx0, "y": cy0, "s": S0, "dip": 0})
    t += OVER
    segs, sfx = [], [("impact", 0.05), ("whoosh", POSTER - 0.2)]
    for i, (s, c) in enumerate(zip(sel, clips)):
        p = P[f"s{i}"]
        arrive = t + FLY
        cam.append({"t": arrive, "x": p["x"], "y": p["y"], "s": SZ, "dip": 0 if i == 0 else 0.55})
        sfx.append(("whoosh", t + 0.1))
        sfx.append(("click", arrive + 0.05))
        seg = {"i": i, "fly": round(t, 2), "arrive": round(arrive, 2), "x": p["x"], "y": p["y"]}
        if c:
            dive = arrive + SIGN
            vstart = dive + DIVE * 0.6
            vend = vstart + float(c.get("dur", 4.0))
            seg.update(dive=round(dive, 2), v0=round(vstart, 2), v1=round(vend, 2), clip=c["file"], kind=c["kind"])
            sfx.append(("impact", vstart))
            cam.append({"t": vend, "x": p["x"], "y": p["y"], "s": SZ, "dip": 0})  # стоим, пока идут кадры
            t = vend
        else:
            seg.update(dive=None)
            t = arrive + SIGN_ONLY
            cam.append({"t": t, "x": p["x"], "y": p["y"], "s": SZ * 1.04, "dip": 0})
        segs.append(seg)
    outro = round(t + 0.15, 2)
    cam.append({"t": outro + 0.6, "x": cx0, "y": cy0 + IH * 0.04, "s": S0 * 1.05, "dip": 0})
    sfx.append(("whoosh", outro - 0.2))
    sfx.append(("impact", outro + 0.9))
    total = round(outro + OUTRO, 2)

    # ── тексты ──
    n = len(day)
    n_fuel = sum(1 for s in day if s["cls"] == 2)
    regions = []
    for s in day:
        r = str(s.get("region") or "").strip()
        r = re.sub(r"\s*область$", " обл.", r)
        if r and r not in regions:
            regions.append(r)
    cities = []
    for s in sel + day:
        c = str(s.get("city") or "").strip()
        if c and c not in cities and len(c) <= 16:
            cities.append(c)
    date_rus = G.rus_date(date)
    signs = []
    for i, s in enumerate(sel):
        conf = "подтверждено" if str(s.get("confidence")).lower() == "confirmed" else "сообщается"
        signs.append(f'''<div class="sign" id="sg{i}"><div class="sg-in">
          <div class="sg-row"><span class="sg-k k{s["cls"]}">{esc(kind_label(s).upper())}</span><span class="sg-d">{esc(G.rus_date_short(date))} · {conf}</span></div>
          <div class="sg-city">{esc(s.get("city") or s.get("region") or "")}</div>
          <div class="sg-obj">{esc(object_name(s, refs))}</div>
          <div class="sg-txt">{esc(what_happened(s))}</div>
        </div><div class="sg-stem"></div></div>''')
    videos, caps = [], []
    for seg in segs:
        if not seg.get("dive"):
            continue
        i = seg["i"]
        s = sel[i]
        dur = round(seg["v1"] - seg["v0"] + 0.35, 2)
        videos.append(f'<div class="fw" id="fw{i}"><video id="v{i}" class="clip" src="assets/{esc(seg["clip"])}" muted playsinline '
                      f'data-start="{seg["v0"]}" data-duration="{dur}" data-track-index="{10 + i}"></video></div>')
        what = "кадры очевидцев" if seg["kind"] == "video" else "фото очевидцев"
        caps.append(f'''<div class="lt" id="lt{i}">
          <div class="lt-top"><i></i>{esc(s.get("city") or "")} · {esc(G.rus_date_short(date))}</div>
          <div class="lt-obj">{esc(object_name(s, refs))}</div>
          <div class="lt-src">{what} · открытые Telegram-каналы</div>
        </div>''')

    marks = []
    for k, p in P.items():
        if k.startswith("d"):
            marks.append({"x": p["x"], "y": p["y"], "sel": 0})
    for i in range(len(sel)):
        p = P[f"s{i}"]
        marks.append({"x": p["x"], "y": p["y"], "sel": 1, "i": i})

    # постер: фон — кадр из клипа главного удара (огонь), нет — фрагмент карты
    poster_bg = "assets/map.jpg"
    # самый яркий/«огненный» кадр клипа ГЛАВНОГО удара (заголовок постера про него — чужой огонь под ним
    # вводил бы в заблуждение); ночной кадр вытягиваем яркостью в CSS-фильтре
    best = None
    for sg in [sg for sg in segs if sg.get("dive")][:1]:
        for ts in (0.6, 1.4, 2.2, 3.0):
            cand = build / "assets" / f"_pc{sg['i']}_{ts}.jpg"
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(ts), "-i",
                                str(build / "assets" / sg["clip"]), "-frames:v", "1", "-q:v", "3", str(cand)])
            if r.returncode or not cand.exists():
                continue
            sc = fire_score(cand)
            if not best or sc > best[0]:
                best = (sc, cand)
    if best:
        best[1].replace(build / "assets" / "poster.jpg")
        poster_bg = "assets/poster.jpg"
    for f in (build / "assets").glob("_pc*.jpg"):
        f.unlink()
    ptitle = poster_head(sel, day, refs)
    pcities = " · ".join(c.upper() for c in cities[:3])

    plan = {"total": total, "poster": POSTER, "cam": cam, "segs": segs, "marks": marks,
            "outro": outro, "IW": IW, "IH": IH, "dive": DIVE}
    subs = {
        "TOTAL": total, "POSTER_END": POSTER + 0.35, "POSTER_BG": poster_bg,
        "POSTER_TITLE": esc(ptitle), "POSTER_TSIZE": 150 if len(ptitle) <= 22 else (124 if len(ptitle) <= 30 else 104),
        "POSTER_CITIES": esc(pcities),
        "POSTER_SUB": esc(f"{date_rus.upper()} · {n} {G.plural(n, 'УДАР', 'УДАРА', 'УДАРОВ')} ЗА СУТКИ"),
        "IW": IW, "IH": IH, "DATE_RUS": esc(date_rus), "DATE_SHORT": esc(G.rus_date_short(date)),
        "SIGNS": "\n".join(signs), "VIDEOS": "\n".join(videos), "CAPS": "\n".join(caps),
        "N": n, "N_WORD": G.plural(n, "удар", "удара", "ударов"),
        "N_FUEL": n_fuel, "N_OTHER": n - n_fuel,
        "FUEL_WORD": "по НПЗ, нефтепроводам и энергетике",
        "REGIONS": esc(", ".join(regions[:5]) + (f" и ещё {len(regions) - 5}" if len(regions) > 5 else "")),
        "SITE": SITE_HOST, "TG": TG_HANDLE,
        "PLAN_JSON": json.dumps(plan).replace("</", "<\\/"),
    }
    page = (TPL / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: str(subs[m.group(1)]), page)
    (build / "index.html").write_text(page, encoding="utf-8")
    (build / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")

    # plan.json в формате ежедневного ролика: его mix() кладёт эффекты + музыку
    mixplan = {"date": date, "total": total,
               "sfx": [{"name": a, "t": round(max(0, x), 2)} for a, x in sfx]}
    (build / "plan.json").write_text(json.dumps(mixplan, ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "description.txt").write_text(describe(date, sel, day, refs, segs, clips), encoding="utf-8")
    print(json.dumps({"date": date, "total": total, "strikes": [s.get("city") for s in sel],
                      "footage": [c and c["src"] for c in clips]}, ensure_ascii=False))


def describe(date, sel, day, refs, segs, clips):
    n = len(day)
    fuel = [s for s in sel if s["cls"] == 2]
    if fuel:
        names = [object_name(s, refs) for s in fuel]
        head = "Удар по " + dative_object(names[0])
        if len(names) > 1:
            head = "Удары по " + dative_object(names[0]) + " и " + names[1]
    else:
        head = f"{n} {G.plural(n, 'удар', 'удара', 'ударов')} по РФ"
    tail = f" · {G.rus_date_short(date)} #shorts"
    if len(head) + len(tail) > 100:
        head = head[:100 - len(tail) - 1].rstrip(" ,.;:—-") + "…"
    lines = [head + tail, "", f"«Топливный фронт РФ»: удары за {G.rus_date(date)} на карте сайта.", ""]
    for s in sel:
        lines.append(f"— {s.get('city')}: {object_name(s, refs)}. {what_happened(s)}")
    n_fuel = sum(1 for s in day if s["cls"] == 2)
    lines += ["", f"Всего за сутки: {n} {G.plural(n, 'удар', 'удара', 'ударов')}, из них {n_fuel} — по НПЗ, "
              f"нефтепроводам и энергетике."]
    src = [c["src"] for c in clips if c]
    if src:
        lines += ["", "Кадры: открытые Telegram-каналы:"] + [f"— {u}" for u in src]
    lines += ["", f"Карта ударов: https://{SITE_HOST}/",
              f"Сводка дня: https://{SITE_HOST}/news/{date}.html",
              f"Telegram-канал: {B.TG_URL}", "",
              "ОЦЕНКА: агрегация открытых источников (OSINT), не официальная информация.", "",
              "#НПЗ #ТопливныйФронт #новости"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["select"] and len(a) == 2:
        sel, day = select_strikes(a[1])
        print(json.dumps([{k: s.get(k) for k in ("city", "target", "confidence", "cls", "lat", "lon", "source_url")}
                          for s in sel], ensure_ascii=False, indent=1), f"\nвсего за день: {len(day)}")
    elif a[:1] == ["prepare"] and len(a) == 3:
        prepare(a[1], Path(a[2]))
    elif a[:1] == ["compose"] and len(a) == 3:
        compose(a[1], Path(a[2]))
    else:
        sys.exit(__doc__)
