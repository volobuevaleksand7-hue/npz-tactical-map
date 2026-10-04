#!/usr/bin/env python3
"""Сборка ежедневного ролика-сводки: данные проекта -> HyperFrames-композиция -> звук.

  python3 video/build.py compose <YYYY-MM-DD> <build_dir>   # index.html + assets + plan.json
  python3 video/build.py mix <build_dir> <silent.mp4> <out.mp4>  # эффекты + музыка, рядом <out>.txt
                                                                 # (заголовок/описание для YouTube)
  python3 video/build.py latest                              # последняя дата сводки

Источник данных — тот же, что у страницы /news/<дата> (agents/gen-news.py):
data/news-archive.json -> briefs[<дата>].strikes; классификация ударов, заголовок
дня, обложка — функциями самого gen-news.py, чтобы ролик и страница не расходились.
Мощности НПЗ — data/fuel-state.json -> refineries[]. Только stdlib.
"""
import hashlib
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO = Path(__file__).resolve().parent
ROOT = VIDEO.parent
TEMPLATE = VIDEO / "template"
SFX = VIDEO / "sfx"
MUSIC = VIDEO / "music"
MUSIC_EXT = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac"}
MAX_CARDS = 3
X = 0.5  # кроссфейд между сценами, должен совпадать с template/index.html


def gen_news():
    spec = importlib.util.spec_from_file_location("gen_news", ROOT / "agents" / "gen-news.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # main() под __name__ == "__main__" — импорт без побочек
    return mod


G = gen_news()
esc = lambda s: html.escape(str(s), quote=True)


def latest_date() -> str:
    dates = sorted(p.stem for p in (ROOT / "news").glob("*.html")
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
    if not dates:
        sys.exit("build.py: в news/ нет ни одной сводки YYYY-MM-DD.html")
    return dates[-1]


# ───────────────────────── НПЗ: сопоставление удара с заводом ─────────────────────────

GENERIC = {"нпз", "лукойл", "газпром", "нефтехим", "группа", "башнефть", "славнефть",
           "роснефть", "гпз", "зск", "эко", "лукойл-пермнефтеоргсинтез"}


def refinery_matchers(refineries):
    """[(regex, refinery)]: «Ильский НПЗ» ловит «Ильский нефтеперерабатывающий…»/«Ильский НПЗ»,
    алиас в скобках («Капотня», «Кстово», «Кинеф») ловится сам по себе."""
    out = []
    for r in refineries:
        name = str(r.get("name", ""))
        pats = []
        first = re.split(r"[\s(]", name.strip(), maxsplit=1)[0]
        if len(first) >= 5 and first.lower() not in GENERIC:
            stem = re.escape(first.lower()[:-2])
            pats.append(stem + r"\w*\s+(?:нпз|нефтеперераб|гпз|зск)")
            pats.append(r"(?:нпз|нефтеперерабатывающий завод)\s+«?" + stem)
        for alias in re.findall(r"\(([^)]+)\)", name):
            a = alias.strip().lower()
            if len(a) >= 4 and a not in GENERIC:
                pats.append(re.escape(a[:-1] if len(a) > 5 else a))
        if pats:
            out.append((re.compile("|".join(pats)), r))
    return out


def clean_target(s: dict) -> str:
    t = str(s.get("target") or s.get("title") or "Объект топливной инфраструктуры").strip()
    t = re.split(r"\s+[—–-]\s+|\s*\(|,|;", t)[0].strip() or t
    t = re.sub(r"нефтеперерабатывающий завод", "НПЗ", t, flags=re.I)
    t = t[:1].upper() + t[1:]
    return t if len(t) <= 60 else t[:58].rstrip() + "…"


def object_kind(s: dict) -> str:
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    for keys, label in ((("нпз", "нефтеперераб"), "НПЗ"), (("терминал", "порт"), "нефтяной терминал"),
                        (("нефтебаз", "нефтепрод", "хранилищ", "депо"), "нефтебаза"), (("нефтехим", "гпз", "газоперераб"), "нефтехимия"),
                        (("танкер", "суд"), "танкеры"), (("перекачк", "нпс", "трубопровод"), "перекачивающая станция"),
                        (("подстанц", "тэц", "тэс", "грэс", "энерг", "электро"), "энергетика")):
        if any(k in t for k in keys):
            return label
    return "топливная инфраструктура"


def fmt_cap(v) -> str:
    try:
        return f"{float(v):.1f}".rstrip("0").rstrip(".").replace(".", ",")
    except (TypeError, ValueError):
        return ""


def pick_cards(strikes, refineries):
    """Удары по НПЗ/энергетике (как считает страница), confirmed + reported, слухи — нет.
    Сортировка — strike_rank из gen-news (лид дня первым), дубли одного объекта склеиваем."""
    matchers = refinery_matchers(refineries)
    ref = [s for s in strikes if G.is_refinery(s)
           and str(s.get("confidence", "reported")).lower() in ("confirmed", "reported")]
    ref.sort(key=G.strike_rank, reverse=True)
    cards, seen = [], {}
    for s in ref:
        text = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
        r = next((r for rx, r in matchers if rx.search(text)), None)
        key = ("r", r["id"]) if r else ("t", clean_target(s).lower())
        conf = "confirmed" if str(s.get("confidence")).lower() == "confirmed" else "reported"
        if key in seen:  # тот же объект: подтверждённость берём лучшую
            if conf == "confirmed":
                seen[key]["conf"] = "confirmed"
            continue
        place = " · ".join(x for x in (str(s.get("city") or "").strip(), str(s.get("region") or "").strip()) if x)
        if r and fmt_cap(r.get("capacity_mt_year")):
            line = f"Мощность <b>{fmt_cap(r['capacity_mt_year'])} млн т</b> нефти в год"
        else:
            line = f"Тип объекта: <b>{esc(object_kind(s))}</b>"
        card = {"name": r["name"] if r else clean_target(s), "place": place, "line": line, "conf": conf}
        seen[key] = card
        cards.append(card)
    return cards


# ───────────────────────── интро: карта ударов (слои /radar) ─────────────────────────
# Карта со страницы /karta-bpla — это iframe /radar: OSM-тайлы из сети + границы регионов
# (data/*.geojson) + удары. Тайлы и «последние 48 часов от сейчас» для ролика не годятся
# (сеть и недетерминизм), поэтому берём те же локальные слои: полигоны регионов,
# подсветку региона под ударом (как .region-hot) и пульсирующие огни ударов за дату
# ролика, а проекцию — ту же Web Mercator, что у Leaflet. Всё рисуется в SVG/HTML
# внутри композиции — рендер не ходит в сеть.

INTRO = 3.8  # с: длина интро до начала кроссфейда в обложку
GEO = [ROOT / "data" / f for f in ("russia-regions-v2.geojson", "new-territories.geojson",
                                   "crimea-regions.geojson")]
W, H = 1080, 1920
LON0, LAT0, DEG = 43.0, 52.5, 1080 / 34  # центр стартового кадра и px на градус долготы
FOCUS_Y = 1010  # куда камера приводит центр скопления ударов


def _merc(lat):
    import math
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(max(-85, min(85, lat))) / 2)))


def proj(lon, lat):
    return (W / 2 + (lon - LON0) * DEG, H / 2 - (_merc(lat) - _merc(LAT0)) * DEG)


def _rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def _inside(x, y, ring):
    ok = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            ok = not ok
    return ok


def _strike_xy(s):
    try:
        lat, lon = float(s["lat"]), float(s["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return (lon, lat) if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon) else None


def intro_pops(n):
    """Моменты появления огней на карте (с): лесенка 0.55..1.85, один в 0.6."""
    return [round(0.55 + 1.3 * i / (n - 1), 2) for i in range(n)] if n > 1 else [0.6] * n


def map_layer(date, strikes, briefs):
    """SVG регионов + точки ударов в координатах стартового кадра + план камеры."""
    pts = []
    for s in sorted(strikes, key=G.strike_rank, reverse=True):
        ll = _strike_xy(s)
        if ll:
            x, y = proj(*ll)
            pts.append({"x": round(x, 1), "y": round(y, 1), "ll": ll,
                        "ref": 1 if G.is_refinery(s) else 0,
                        "city": str(s.get("city") or s.get("region") or "").strip()})
    # фон недели: удары за 7 предыдущих дней — тусклые точки, без пульса
    from datetime import date as _d, timedelta
    d0 = _d.fromisoformat(date)
    week = []
    for k in range(1, 8):
        for s in briefs.get((d0 - timedelta(days=k)).isoformat(), {}).get("strikes", []):
            ll = _strike_xy(G.normalize_strike(s))
            if ll:
                x, y = proj(*ll)
                week.append([round(x, 1), round(y, 1)])

    # регионы: SVG-пути; «горячие» — где лежит удар дня (point-in-polygon, имена в данных
    # и в geojson расходятся: «Республика Татарстан» против «Татарстан»)
    paths, hot = [], set()
    feats = []
    for f in GEO:
        try:
            feats += json.loads(f.read_text(encoding="utf-8")).get("features", [])
        except (OSError, ValueError):
            continue
    for fi, ft in enumerate(feats):
        polys = _rings(ft.get("geometry") or {})
        for p in pts:
            if any(_inside(p["ll"][0], p["ll"][1], [tuple(c[:2]) for c in poly[0]]) for poly in polys):
                hot.add(fi)
        d = []
        for poly in polys:
            for ring in poly:
                xy = [proj(c[0], c[1]) for c in ring if c[0] > 0]  # Чукотка за антимеридианом — вне кадра
                if len(xy) < 3 or min(x for x, _ in xy) > W * 2.2:
                    continue
                d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in xy) + "Z")
        if d:
            paths.append(f'<path class="rg{" hot" if fi in hot else ""}" d="{"".join(d)}"/>')
    grid = []
    for lon in range(10, 100, 5):
        x = proj(lon, 0)[0]
        grid.append(f'<path class="gr" d="M{x:.1f},-2000L{x:.1f},4000"/>')
    for lat in range(30, 80, 5):
        y = proj(LON0, lat)[1]
        grid.append(f'<path class="gr" d="M-2000,{y:.1f}L4000,{y:.1f}"/>')
    svg = (f'<svg class="geo" width="{W}" height="{H}" viewBox="0 0 {W} {H}" overflow="visible" '
           f'xmlns="http://www.w3.org/2000/svg">{"".join(grid)}{"".join(paths)}</svg>')

    # камера: к самому плотному скоплению ударов дня (сосед — ближе 9° по меркатору),
    # зум — чтобы скопление заняло ~60% ширины, 1.5..3.0; нет ударов — к фону недели
    src = [(p["x"], p["y"]) for p in pts] or [tuple(w) for w in week]
    if src:
        r = 9 * DEG
        best = max(src, key=lambda a: sum(1 for b in src if (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 < r * r))
        cl = [b for b in src if (best[0] - b[0]) ** 2 + (best[1] - b[1]) ** 2 < r * r]
        xs, ys = [c[0] for c in cl], [c[1] for c in cl]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max(max(xs) - min(xs), (max(ys) - min(ys)) * 0.6, 1)
        z = max(1.5, min(3.0, W * 0.6 / span)) if pts else 1.5
    else:
        cx, cy, z = W / 2, H / 2, 1.3
    cam = {"x0": W / 2, "y0": H / 2, "x1": round(cx, 1), "y1": round(cy, 1), "z": round(z, 2), "fy": FOCUS_Y}

    # подписи городов — по финальному кадру, без наложений, не больше 4
    labels, boxes = [], []
    for i, p in enumerate(pts):
        if not p["city"] or len(labels) >= 4 or p["city"] in [l["text"] for l in labels]:
            continue
        sx, sy = W / 2 + (p["x"] - cx) * z, FOCUS_Y + (p["y"] - cy) * z
        tw = 22 * len(p["city"]) + 30
        side = 1 if sx + 40 + tw < W - 40 else -1
        bx = (sx + 34, sx + 34 + tw) if side > 0 else (sx - 34 - tw, sx - 34)
        box = (bx[0], sy - 26, bx[1], sy + 26)
        if box[0] < 30 or box[2] > W - 30 or box[1] < 330 or box[3] > H - 420 or \
                any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in boxes):
            continue
        boxes.append(box)
        labels.append({"i": i, "text": p["city"][:24], "side": side})
    for p, t in zip(pts, intro_pops(len(pts))):
        del p["ll"]
        p["t"] = t
    return svg, {"cam": cam, "pts": pts, "week": week, "labels": labels}


# ───────────────────────────────── compose ─────────────────────────────────

def poster_text(strikes: list) -> dict:
    """Текст постера S1 (он же обложка Shorts): число, «ударов по РФ», лид дня, города."""
    n = len(strikes)
    if not n:
        return {"head": "ударов за сутки", "lead": "Сводка: без подтверждённых ударов", "cities": ""}
    ranked = sorted(strikes, key=G.strike_rank, reverse=True)
    lead = ranked[0]
    city = str(lead.get("city", "")).strip()
    if G.is_refinery(lead):
        lead_txt = f"Удар по {G.infra_label(lead)} в {G._prep_city(city)}"
    elif lead.get("title"):
        lead_txt = str(lead["title"]).strip().rstrip(".")
    else:
        lead_txt = f"{city}: {clean_target(lead)}" if city else clean_target(lead)
    cities = []
    for x in ranked:
        c = str(x.get("city", "")).strip()
        if c and c != city and c not in cities:
            cities.append(c)
    line = " · ".join(cities[:3])
    if len(cities) > 3:
        line += f" и ещё {len(cities) - 3}"
    return {"head": f"{G.plural(n, 'удар', 'удара', 'ударов')} по РФ", "lead": lead_txt, "cities": line}


def compose(date: str, build: Path):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        sys.exit(f"build.py: дата должна быть YYYY-MM-DD, получено {date!r}")
    archive = json.loads((ROOT / "data" / "news-archive.json").read_text(encoding="utf-8"))
    briefs = archive.get("briefs", {})
    if date not in briefs:
        sys.exit(f"build.py: в data/news-archive.json нет сводки за {date}")
    strikes = [G.normalize_strike(s) for s in briefs[date].get("strikes", [])]
    fuel = json.loads((ROOT / "data" / "fuel-state.json").read_text(encoding="utf-8"))

    n = len(strikes)
    n_ref = sum(1 for s in strikes if G.is_refinery(s))
    cards = pick_cards(strikes, fuel.get("refineries", []))
    shown, more = cards[:MAX_CARDS], max(0, len(cards) - MAX_CARDS)

    # тайминги: интро-карта [0, s1+X], дальше сцены как раньше, сдвинутые на s1
    s1 = INTRO
    s2 = round(s1 + 4.2, 2)
    s3 = s2 + 4.0 if shown else None
    card_t = [round(s3 + 1.1 + 1.15 * i, 2) for i in range(len(shown))] if shown else []
    more_t = round(card_t[-1] + 1.0, 2) if more else None
    s3_dur = (max(4.2, 2.6 + 1.15 * len(shown) + (0.9 if more else 0)) if shown else 0)
    s4 = round((s3 + s3_dur) if shown else s2 + 4.0, 2)
    total = round(s4 + 4.8, 2)

    # обложка: тот же выбор, что у og:image страницы; нет — общая og-image.png (как на сайте)
    cover_rel, cover_ok = G.cover_for(date)
    cover_src = ROOT / (cover_rel if cover_ok else "og-image.png")

    if build.exists():
        shutil.rmtree(build)
    (build / "assets").mkdir(parents=True)
    shutil.copytree(TEMPLATE / "assets" / "fonts", build / "assets" / "fonts")
    shutil.copy2(cover_src, build / "assets" / ("cover" + cover_src.suffix))
    gsap = VIDEO / "node_modules" / "gsap" / "dist" / "gsap.min.js"
    if not gsap.exists():
        sys.exit("build.py: нет node_modules/gsap — выполните `npm ci` в video/")
    shutil.copy2(gsap, build / "assets" / "gsap.min.js")

    if shown:
        cards_html = "\n".join(
            f'''          <div class="card {c["conf"]}" id="c{i + 1}">
            <div class="row"><span class="tag">{"Подтверждено" if c["conf"] == "confirmed" else "Сообщается"}</span><span class="city">{esc(c["place"])}</span></div>
            <h3>{esc(c["name"])}</h3>
            <p>{c["line"]}</p>
          </div>''' for i, c in enumerate(shown))
        if more:
            cards_html += (f'\n          <div class="more">и ещё {more} '
                           f'{G.plural(more, "объект", "объекта", "объектов")}</div>')
        s3_block = f'''<div id="s3" class="scene clip n{len(shown)}" data-start="{s3}" data-duration="{round(s3_dur + X, 2)}" data-track-index="3">
        <div class="brand" data-layout-allow-overlap><i></i>СВОДКА · {G.rus_date_short(date)}</div>
        <div class="hd">Удары по НПЗ<br />и энергетике</div>
        <div class="list">
{cards_html}
        </div>
        <div class="bar"></div>
      </div>'''
    else:
        s3_block = "<!-- S3 пропущена: за день нет ударов по НПЗ/энергетике -->"

    if n_ref:
        pill = f'<div class="pill">{n_ref} по НПЗ/энергетике</div>'
    else:
        pill = '<div class="pill calm">по НПЗ — без ударов</div>'
    stats = [f'<span>{n} {G.plural(n, "удар", "удара", "ударов")}</span>']
    if n_ref:
        stats.append(f'<span class="r">{n_ref} по НПЗ/энергетике</span>')

    geo_svg, geo = map_layer(date, strikes, briefs)
    if n:
        cap = f'<b>{n}</b> {G.plural(n, "удар", "удара", "ударов")} за сутки'
    else:
        cap = 'За сутки ударов <b>не зафиксировано</b>'
    legend = ('<span><i class="lg day"></i>удары за сутки</span>' if geo["pts"] else "") + \
             ('<span><i class="lg lw"></i>за прошлую неделю</span>' if geo["week"] else "")

    poster = poster_text(strikes)
    plan = {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "total": total, "count": n,
            "cards": card_t, "more": more_t, "geo": geo}
    host = G.SITE.split("://", 1)[-1]
    subs = {
        "TOTAL": total, "S0_DUR": round(s1 + X, 2), "S1_START": s1,
        "S1_DUR": round(s2 - s1 + X, 2), "S2_START": s2,
        "GEO_SVG": geo_svg, "MAP_CAPTION": cap, "MAP_LEGEND": legend,
        "MAP_DATE": esc(G.rus_date(date).upper()),
        "MAP_TITLE": esc(f"{n} {G.plural(n, 'удар', 'удара', 'ударов')} по РФ" if n else "Карта ударов"),
        "POSTER_NUM": n, "POSTER_NUM_SIZE": 420 if n < 10 else 380 if n < 100 else 300,
        "POSTER_HEAD": esc(poster["head"]), "POSTER_LEAD": esc(poster["lead"]),
        "POSTER_CITIES": esc(poster["cities"]),
        "S2_DUR": round(((s3 if shown else s4) - s2) + X, 2),
        "S4_START": s4, "S4_DUR": round(total - s4, 2),
        "COVER": "assets/cover" + cover_src.suffix,
        "WEEKDAY_DATE": esc(f"{G.weekday_ru(date).upper()}, {G.rus_date_short(date)}"),
        "DATE_RUS": esc(G.rus_date(date)), "DATE_SHORT": esc(G.rus_date_short(date)),
        "BIG_SIZE": 560 if n < 100 else 400, "BIG_INITIAL": 0,
        "STRIKES_WORD": G.plural(n, "удар", "удара", "ударов"),
        "PILL": pill, "S3_BLOCK": s3_block,
        "HEADLINE": esc(G.brief_headline(date, strikes)), "STATS": "".join(stats),
        "URL_HOST": esc(host + "/"), "URL_PATH": esc(f"news/{date}"),
        "PLAN_JSON": json.dumps(plan).replace("</", "<\\/"),
    }
    page = (TEMPLATE / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: str(subs[m.group(1)]), page)
    (build / "index.html").write_text(page, encoding="utf-8")
    (build / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")

    # звуковые события для mix: вжух на каждой смене сцены, удар на цифре, щелчки на карточках
    # интро: глухой удар на старте, щелчки на первых огнях, вжух в обложку
    events = [("impact", 0.15)]
    events += [("click", round(t, 2)) for t in intro_pops(len(geo["pts"]))[:5]]
    events.append(("whoosh", s1 - 0.25))
    events.append(("whoosh", s2 - 0.25))
    events.append(("impact", s2 + (1.5 if n > 0 else 0.45)))
    if shown:
        events.append(("whoosh", s3 - 0.25))
        events += [("click", t + 0.05) for t in card_t]
        if more_t:
            events.append(("click", more_t + 0.05))
    events.append(("whoosh", s4 - 0.25))
    plan.update(date=date, cover=str(cover_src.relative_to(ROOT)), strikes=n, refinery_strikes=n_ref,
                cards_total=len(cards), cards_shown=[c["name"] for c in shown],
                sfx=[{"name": a, "t": round(t, 2)} for a, t in events])
    plan.pop("geo")
    (build / "description.txt").write_text(describe(date, strikes, n_ref, cards), encoding="utf-8")
    (build / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: plan[k] for k in ("date", "total", "strikes", "refinery_strikes",
                                           "cards_total", "cards_shown", "cover")}, ensure_ascii=False))


# ─────────────────────────── описание для YouTube ───────────────────────────

TG_URL = "https://t.me/npz_karta_online"  # тот же канал, что у баннера сайта


def describe(date: str, strikes: list, n_ref: int, cards: list) -> str:
    """Заголовок (1-я строка, <=100 символов, с #shorts) + описание ролика."""
    n = len(strikes)
    tail = f" · {G.rus_date_short(date)} #shorts"
    head = G.brief_headline(date, strikes)
    if len(head) + len(tail) > 100:
        head = head[:100 - len(tail) - 1].rstrip(" ,.;:—-") + "…"
    lines = [head + tail, "",
             f"Сводка «Топливный фронт РФ» за {G.rus_date(date)} ({G.weekday_ru(date)}).", ""]
    if n:
        s = f"За сутки зафиксировано {n} {G.plural(n, 'удар', 'удара', 'ударов')}"
        lines.append(s + (f", из них {n_ref} — по НПЗ и энергетике." if n_ref else
                          ", по НПЗ и энергетике — без ударов."))
        if cards:
            lines.append("")
            lines.append("Объекты:")
            for c in cards[:5]:
                st = "подтверждено" if c["conf"] == "confirmed" else "сообщается"
                lines.append(f"— {c['name']}" + (f" ({c['place']})" if c["place"] else "") + f" — {st}")
            if len(cards) > 5:
                lines.append(f"— и ещё {len(cards) - 5}")
        regions = []
        for x in strikes:
            r = str(x.get("region") or "").strip()
            if r and r not in regions:
                regions.append(r)
        if regions:
            lines += ["", "Регионы: " + ", ".join(regions[:8]) + (" и др." if len(regions) > 8 else "") + "."]
    else:
        lines.append("За сутки ударов не зафиксировано. На карте — удары за прошлую неделю.")
    lines += ["",
              f"Полная сводка на сайте: {G.SITE}/news/{date}.html",
              f"Карта ударов и свежие сводки — в Telegram-канале: {TG_URL}",
              "Подписывайтесь, чтобы не пропустить следующую сводку.",
              "",
              "ОЦЕНКА: агрегация открытых источников (OSINT), не официальная информация.",
              "",
              "#НПЗ #ТопливныйФронт #новости"]
    return "\n".join(lines) + "\n"


# ───────────────────────────────── mix ─────────────────────────────────

SFX_GAIN = {"whoosh": 1.6, "impact": 1.0, "click": 0.8}


def music_files():
    return sorted(p for p in MUSIC.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXT) \
        if MUSIC.is_dir() else []


def ensure_music():
    """Нет ни одного трека — синтезируем свои (music/make-music.sh, только ffmpeg).
    Сбой синтеза не роняет рендер: ролик выйдет с одними эффектами."""
    if music_files() or not (MUSIC / "make-music.sh").exists():
        return
    try:
        subprocess.run(["bash", str(MUSIC / "make-music.sh")], check=True, timeout=300)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"mix: музыку синтезировать не удалось ({e}) — только эффекты", file=sys.stderr)


def pick_music(date: str):
    ensure_music()
    files = music_files()
    if not files:
        return None
    # детерминированно «по дате»: тот же день -> тот же трек, соседние дни — разные
    idx = int(hashlib.md5(date.encode()).hexdigest(), 16) % len(files)
    return files[idx]


def mix(build: Path, silent: Path, out: Path):
    plan = json.loads((build / "plan.json").read_text(encoding="utf-8"))
    total = plan["total"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent)]
    parts, labels = [], []
    for i, ev in enumerate(plan["sfx"]):
        cmd += ["-i", str(SFX / f"{ev['name']}.wav")]
        ms = max(0, int(ev["t"] * 1000))
        parts.append(f"[{i + 1}:a]volume={SFX_GAIN[ev['name']]},adelay={ms}|{ms}[e{i}]")
        labels.append(f"[e{i}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
                 f"apad=whole_dur={total}[fx]")  # конечная длина: бесконечный apad вешал ffmpeg
    music = pick_music(plan["date"])
    if music:
        mi = len(plan["sfx"]) + 1
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        parts.append("[fx]asplit=2[fxa][fxb]")
        parts.append(f"[{mi}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total},"
                     f"volume=0.32,afade=t=in:st=0:d=1.2,afade=t=out:st={max(0, total - 1.8)}:d=1.8[mu]")
        # музыка приседает под эффекты (sidechain), эффекты остаются на переднем плане
        parts.append("[mu][fxb]sidechaincompress=threshold=0.03:ratio=8:attack=5:release=350[duck]")
        parts.append("[duck][fxa]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    else:
        parts.append("[fx]alimiter=limit=0.95[aout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", str(total),
            "-movflags", "+faststart", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True, timeout=300)
    desc = build / "description.txt"
    if desc.exists():  # out может быть *.tmp.mp4 — описание кладём под финальное имя
        shutil.copy2(desc, out.parent / (out.name.split(".")[0] + ".txt"))
    print(f"mix: {out.name} (музыка: {music.name if music else 'нет — только эффекты'})")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["latest"]:
        print(latest_date())
    elif a[:1] == ["compose"] and len(a) == 3:
        compose(a[1], Path(a[2]))
    elif a[:1] == ["mix"] and len(a) == 4:
        mix(Path(a[1]), Path(a[2]), Path(a[3]))
    else:
        sys.exit(__doc__)
