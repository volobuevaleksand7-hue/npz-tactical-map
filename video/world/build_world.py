#!/usr/bin/env python3
"""Ролик про Индекс топливной напряжённости (ИТН / FTI), /world. Вертикаль 1080x1920, RU или EN.

  python3 world/build_world.py compose <ru|en> <build_dir> [YYYY-MM-DD]   # озвучка + index.html + plan.json + description.txt
Дальше как у рилсов: hyperframes render -> `build.py mix` (эффекты+музыка) -> out/world-<дата>.mp4 / out/en-world-<дата>.mp4
(см. world/render_world.sh). Все числа берутся из data/world/*.json и data/world/series.json; события — три
последние review=approved (тексты — world/event_texts.json, EN-перевод там же, написан вручную).
Карта — SVG из lab/world-countries.geojson (то же, что на странице /world), без сети.
"""
import json
import math
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO = HERE.parent
ROOT = VIDEO.parent
sys.path.insert(0, str(VIDEO / "reel"))

SITE = "npz-tactical-map.vercel.app/world"
SITE_URL = "https://npz-tactical-map.vercel.app/world"
TG = "@npz_karta_online"
TG_URL = "https://t.me/npz_karta_online"
VOICES = {"ru": ("ru-RU-DmitryNeural", "+25%"), "en": ("en-US-ChristopherNeural", "+10%")}
LEVEL_COLOR = {"critical": "#e5483b", "crisis": "#e8843f", "tense": "#d9b04a", "calm": "#46b08a"}
LEVEL_EN = {"critical": "critical", "crisis": "crisis", "tense": "tense", "calm": "calm"}
REGION_EN = {"north_america": "North America", "east_asia": "East Asia & Pacific", "europe": "Europe",
             "middle_east": "Middle East", "south_asia": "South Asia", "latin_america": "Latin America",
             "russia_cis": "Russia & CIS", "africa": "Africa"}
# подпись региона на карте (короткая) и якорь (lon, lat)
REGION_ANCHOR = {"north_america": (-100, 46), "latin_america": (-62, -12), "europe": (14, 51), "africa": (20, 3),
                 "middle_east": (44, 26), "south_asia": (79, 21), "east_asia": (112, 33), "russia_cis": (80, 63)}
REGION_SHORT = {"ru": {"north_america": "С.Америка", "east_asia": "В.Азия", "europe": "Европа", "middle_east": "Б.Восток",
                       "south_asia": "Ю.Азия", "latin_america": "Л.Америка", "russia_cis": "РФ/СНГ", "africa": "Африка"},
                "en": {"north_america": "N.America", "east_asia": "E.Asia", "europe": "Europe", "middle_east": "Mid.East",
                       "south_asia": "S.Asia", "latin_america": "L.America", "russia_cis": "RU/CIS", "africa": "Africa"}}
RU_DAT = {"latin_america": "Латинской Америке"}
RU_MONTH = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
EN_MONTH = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MW = 1080.0  # ширина карты в базовых пикселях


def jload(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def fnum(x, lang, dec=None):
    s = f"{x:.{dec}f}" if dec is not None else f"{x:g}"
    return s.replace(".", ",") if lang == "ru" else s


def fdate(d, lang):  # YYYY-MM-DD
    y, m, dd = d.split("-")
    return f"{dd}.{m}.{y}" if lang == "ru" else f"{EN_MONTH[int(m) - 1]} {int(dd)}, {y}"


# ───────────────────────── карта ─────────────────────────
def _my(lat):  # проекция Miller
    return 1.25 * math.log(math.tan(math.pi / 4 + 0.4 * math.radians(lat)))


LON0, LAT_TOP, LAT_BOT = -170.0, 84.0, -56.0
K = MW / 360.0 * (180 / math.pi) * 0 + MW / (2 * math.pi) * (2 * math.pi / 360) * 0  # не используется
SCALE = MW / math.radians(360)  # px на радиан по x


def proj(lon, lat):
    return (lon - LON0) / 360.0 * MW, (_my(LAT_TOP) - _my(lat)) * SCALE


MH = proj(0, LAT_BOT)[1]


def map_paths(index):
    gj = jload("lab/world-countries.geojson")
    out = []
    for ft in gj["features"]:
        r = ft["properties"].get("r")
        reg = index["regions"].get(r) if r else None
        if reg is None:
            col = "#26323a"          # вне регионов индекса
        elif reg.get("value") is None:
            col = "url(#hatch)"      # мало данных
        else:
            col = LEVEL_COLOR[reg["level"]]
        g = ft["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = []
        for poly in polys:
            if min(c[0] for c in poly[0]) < -200:   # дубль чукотского полигона, сдвинутый на -360
                continue
            for ring in poly:
                pts, last = [], None
                for lon, lat in ring:
                    x, y = proj(lon, max(lat, -57))
                    if last and abs(x - last[0]) < 0.5 and abs(y - last[1]) < 0.5:
                        continue
                    pts.append((x, y))
                    last = (x, y)
                if len(pts) >= 3:
                    d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        if d:
            out.append(f'<path d="{"".join(d)}" fill="{col}" fill-opacity="{0.9 if reg and reg.get("value") is not None else 0.75}"/>')
    return "".join(out)


# ───────────────────────── данные ─────────────────────────
def collect(lang):
    idx = jload("data/world/index.json")
    hist = jload("data/world/index-history.json")
    series = jload("data/world/series.json")["series"]
    events_all = jload("data/world/events.json")["events"]
    texts = json.loads((HERE / "event_texts.json").read_text(encoding="utf-8"))
    w = idx["world"]
    regs = idx["regions"]
    ranked = sorted([(k, r) for k, r in regs.items() if r.get("value") is not None], key=lambda kv: -kv[1]["value"])
    nodata = [k for k, r in regs.items() if r.get("value") is None]
    gen = idx["generated_at"]
    data_date = gen[:10]
    # Ормуз и дизель — из компонентов индекса (raw) и рядов
    hormuz = None
    for r in regs.values():
        for c in r["components"]:
            m = re.search(r"Ормуз: ([\d,]+) танк\./сут\. при медиане года ([\d,]+)", c.get("raw") or "")
            if c["id"] == "chokepoints" and m:
                hormuz = {"now": float(m.group(1).replace(",", ".")), "med": float(m.group(2).replace(",", ".")),
                          "as_of": c["as_of"], "src": c["source"]}
    pcts = []
    for k in ("north_america", "europe"):
        for c in regs[k]["components"]:
            m = re.search(r"\(p(\d+) к 5 годам", c.get("raw") or "")
            if c["id"] == "retail" and m:
                pcts.append(int(m.group(1)))
    us, eu = series["diesel_retail_us"], series["eu_diesel_retail"]
    if not hormuz or not pcts or us.get("stale") or eu.get("stale"):
        sys.exit("build_world: нет свежих данных для сцены «что двигает индекс» (Ормуз/дизель)")
    ev = [e for e in events_all if e.get("review") == "approved" and e["id"] in texts]
    ev.sort(key=lambda e: (e["occurred_at"], e.get("approved_at", "")), reverse=True)
    ev = ev[:3]
    if not ev:
        sys.exit("build_world: нет одобренных событий с текстами в event_texts.json")
    prev = [h for h in hist if h["date"] < data_date]
    return dict(idx=idx, w=w, regs=regs, ranked=ranked, nodata=nodata, gen=gen, data_date=data_date,
                hormuz=hormuz, pct=min(pcts), us=us, eu=eu, events=ev, texts=texts, prev=prev[-1] if prev else None)


def src_names(e, n=2):
    names = [re.sub(r"\s*\(.*?\)", "", s["publisher"]).strip() for s in e["sources"]]
    return " · ".join(names[:n])


# ───────────────────────── тексты ─────────────────────────
def build_text(lang, D):
    ru = lang == "ru"
    w, regs, rk = D["w"], D["regs"], D["ranked"]
    v, d1 = w["value"], w.get("delta_1d")
    lvl = w["level_ru"] if ru else LEVEL_EN[w["level"]]
    nm = lambda k: regs[k]["name"] if ru else REGION_EN[k]
    dstr = ""
    if d1:
        dstr = (f"За сутки — {'минус' if d1 < 0 else 'плюс'} {abs(d1)}." if ru
                else f"Over the day, {'down' if d1 < 0 else 'up'} {abs(d1)}.")
    hook = (f"Мир на уровне {v} из ста. {lvl.capitalize()}. {dstr}" if ru
            else f"The world is at {v} out of one hundred. {lvl.capitalize()}. {dstr}")
    t1, t2, t3 = rk[0], rk[1], rk[2]
    mapv = (f"{len(regs)} регионов. Выше всех — {nm(t1[0])}, {t1[1]['value']}. Затем {nm(t2[0])}, {t2[1]['value']}, "
            f"и {nm(t3[0])}, {t3[1]['value']}." if ru else
            f"{len(regs)} regions. Highest: {nm(t1[0])}, {t1[1]['value']}. Then {nm(t2[0])}, {t2[1]['value']}, "
            f"and {nm(t3[0])}, {t3[1]['value']}.")
    h = D["hormuz"]
    pc = D["pct"]
    if ru:
        top = "в верхнем проценте за пять лет" if pc >= 99 else f"выше {pc}-го процентиля за пять лет"
        drv = (f"Что двигает индекс. Ормузский пролив: {fnum(h['now'], 'ru')} танкера в сутки при годовой медиане "
               f"{fnum(h['med'], 'ru')}. И дизель: в США {fnum(D['us']['value'], 'ru', 2)} доллара за галлон, в Европе "
               f"{round(D['eu']['value'])} евро за тысячу литров — {top}.")
    else:
        top = "in the top one percent of five years" if pc >= 99 else f"above the {pc}th percentile of five years"
        drv = (f"What drives the index. The Strait of Hormuz: {fnum(h['now'], 'en')} tankers a day against a one-year "
               f"median of {fnum(h['med'], 'en')}. And diesel: {fnum(D['us']['value'], 'en', 2)} dollars a gallon in the US, "
               f"{round(D['eu']['value'])} euros per thousand litres in Europe, {top}.")
    outro = ("Индекс — оценка по открытым данным, методика открыта. Карта и расчёт — на сайте, ссылка в шапке канала."
             if ru else "The index is an open-data estimate, and the methodology is open. Map and calculation on the site; link in the channel header.")
    evv = [D["texts"][e["id"]]["ru_voice" if ru else "en_voice"] for e in D["events"]]
    return dict(hook=hook, map=mapv, drivers=drv, events=evv, outro=outro)


def ui_strings(lang, D):
    ru = lang == "ru"
    regs, w = D["regs"], D["w"]
    nm = lambda k: regs[k]["name"] if ru else REGION_EN[k]
    lvl = (lambda l, r: r["level_ru"] if ru else LEVEL_EN[l])
    h = D["hormuz"]
    return {
        "brand": "ВСЕМИРНЫЙ ТОПЛИВНЫЙ ФРОНТ" if ru else "WORLD FUEL FRONT",
        "stamp": "ОЦЕНКА · OSINT" if ru else "ESTIMATE · OSINT",
        "title": "Индекс топливной напряжённости" if ru else "Fuel Tension Index",
        "abbr": "ИТН" if ru else "FTI",
        "of100": "из 100" if ru else "of 100",
        "level": w["level_ru"].upper() if ru else LEVEL_EN[w["level"]].upper(),
        "delta": ((f"{'−' if w['delta_1d'] < 0 else '+'}{abs(w['delta_1d'])} за сутки" if ru else
                   f"{'−' if w['delta_1d'] < 0 else '+'}{abs(w['delta_1d'])} in a day") if w.get("delta_1d") else ""),
        "asof": (f"Данные на {fdate(D['data_date'], lang)}" if ru else f"Data as of {fdate(D['data_date'], lang)}"),
        "map_head": (f"{len(regs)} регионов · охват данных {round(w['coverage'] * 100)}%" if ru
                     else f"{len(regs)} regions · data coverage {round(w['coverage'] * 100)}%"),
        "nodata": "мало данных" if ru else "not enough data",
        "drv_head": "ЧТО ДВИГАЕТ ИНДЕКС" if ru else "WHAT DRIVES THE INDEX",
        "h_title": "Ормузский пролив" if ru else "Strait of Hormuz",
        "h_now": fnum(h["now"], lang), "h_med": fnum(h["med"], lang),
        "h_unit": "танкера в сутки" if ru else "tankers a day",
        "h_med_lbl": "медиана года" if ru else "one-year median",
        "h_src": f"{h['src']} · {fdate(h['as_of'], lang)} · " + ("7-дн. среднее" if ru else "7-day average"),
        "d_title": "Дизель, розница" if ru else "Retail diesel",
        "d_us": (f"США {fnum(D['us']['value'], lang, 2)} $/гал." if ru else f"US ${fnum(D['us']['value'], lang, 2)}/gal"),
        "d_eu": (f"ЕС {round(D['eu']['value'])} €/1000 л" if ru else f"EU €{round(D['eu']['value'])}/1000 L"),
        "d_pct": (f"процентиль {D['pct']}+ к 5 годам" if ru else f"{D['pct']}th+ percentile vs 5 years"),
        "d_src": ("FRED/EIA · EU Weekly Oil Bulletin · " if ru else "FRED/EIA · EU Weekly Oil Bulletin · ") + fdate(D["us"]["as_of"], lang),
        "ev_head": "СВЕЖИЕ СОБЫТИЯ" if ru else "LATEST EVENTS",
        "ev_src": "Источники" if ru else "Sources",
        "ev_conf": {"confirmed": "ПОДТВЕРЖДЕНО", "reported": "СООБЩАЕТСЯ"} if ru else {"confirmed": "CONFIRMED", "reported": "REPORTED"},
        "out_a": "ИТН — оценка OSINT" if ru else "FTI is an OSINT estimate",
        "out_b": "Методика открыта" if ru else "The methodology is open",
        "out_site": SITE, "out_tg": f"Telegram: {TG}",
        "out_plate": "Ссылка в шапке канала" if ru else "Link in the channel header",
        "out_foot": (f"Не официальные данные · методика v{D['idx']['methodology_version']} · расчёт {D['gen'][11:16]} UTC {fdate(D['data_date'], lang)}"
                     if ru else f"Not official data · methodology v{D['idx']['methodology_version']} · computed {D['gen'][11:16]} UTC {fdate(D['data_date'], lang)}"),
    }


# ───────────────────────── озвучка и тайминги ─────────────────────────
def synth(lang, T, vdir):
    import tts_cascade
    keys = ["hook", "map", "drivers"] + [f"ev{i}" for i in range(len(T["events"]))] + ["outro"]
    lines = [T["hook"], T["map"], T["drivers"]] + list(T["events"]) + [T["outro"]]
    voice, rate = VOICES[lang]
    if os.environ.get("WORLD_NOVOICE"):  # только для локального превью вёрстки: длительности по числу знаков
        return keys, [len(t) / (15.0 if lang == "ru" else 14.0) for t in lines]
    pid, durs = tts_cascade.synth_all([(t, vdir / f"{k}.mp3") for k, t in zip(keys, lines)], lang, voice, rate)
    if pid is None:
        sys.exit("build_world: голос не сгенерирован ни одним провайдером")
    return keys, durs


MIN_LEN = {"hook": 3.4, "map": 6.5, "drivers": 8.5, "ev": 5.2, "outro": 6.0}


def compose(lang, build, date=None):
    D = collect(lang)
    date = date or D["data_date"]
    shutil.rmtree(build, ignore_errors=True)
    (build / "voice").mkdir(parents=True)
    (build / "assets").mkdir()
    shutil.copytree(VIDEO / "template" / "assets" / "fonts", build / "assets" / "fonts")
    shutil.copy2(VIDEO / "node_modules" / "gsap" / "dist" / "gsap.min.js", build / "assets" / "gsap.min.js")
    T = build_text(lang, D)
    U = ui_strings(lang, D)
    keys, durs = synth(lang, T, build / "voice")
    # сцены
    scenes, t = [], 0.0
    for k, dur in zip(keys, durs):
        mn = MIN_LEN["ev"] if k.startswith("ev") else MIN_LEN[k]
        lead = 0.1 if k == "hook" else 0.25
        ln = max(mn, lead + dur + 0.35)
        scenes.append({"id": k, "t0": round(t, 2), "t1": round(t + ln, 2), "voice_t": round(t + lead, 2)})
        t += ln
    total = round(t, 2)
    sc = {s["id"]: s for s in scenes}
    # камера: (t, масштаб, точка карты px/py, куда на экране sx/sy)
    mw_c = (MW / 2, MH / 2)
    hz = proj(56.25, 26.57)
    cam = [
        {"t": 0, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 1470},
        {"t": sc["hook"]["t1"] - 0.2, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 1470},
        {"t": sc["map"]["t0"] + 0.9, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 700},
        {"t": sc["map"]["t1"] - 0.3, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 700},
        {"t": sc["drivers"]["t0"] + 1.4, "s": 3.3, "px": hz[0], "py": hz[1], "sx": 540, "sy": 600},
        {"t": sc["drivers"]["t1"], "s": 3.3, "px": hz[0], "py": hz[1], "sx": 540, "sy": 600},
    ]
    evs = []
    for i, e in enumerate(D["events"]):
        s = sc[f"ev{i}"]
        p = proj(e["lon"], e["lat"])
        z = 2.6 if e.get("radius_km", 0) < 300 else 1.9
        cam.append({"t": s["t0"] + 1.0, "s": z, "px": p[0], "py": p[1], "sx": 540, "sy": 600})
        cam.append({"t": s["t1"], "s": z, "px": p[0], "py": p[1], "sx": 540, "sy": 600})
        tx = D["texts"][e["id"]]
        evs.append({"i": i, "px": p[0], "py": p[1], "r": max(e.get("radius_km", 50) / 111 * MW / 360 * 1.2, 5),
                    "date": fdate(e["occurred_at"], lang),
                    "region": regs_name(D, e["region"], lang),
                    "status": U["ev_conf"][e["status"]], "conf": e["status"],
                    "text": tx["ru_card" if lang == "ru" else "en_card"], "src": src_names(e)})
    cam.append({"t": sc["outro"]["t0"] + 0.6, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 700})
    cam.append({"t": total, "s": 1.0, "px": mw_c[0], "py": mw_c[1], "sx": 540, "sy": 700})
    # метки регионов на карте
    labels = []
    for n, (k, r) in enumerate(D["ranked"] + [(k, D["regs"][k]) for k in D["nodata"]]):
        px, py = proj(*REGION_ANCHOR[k])
        labels.append({"k": k, "px": px, "py": py, "name": REGION_SHORT[lang][k],
                       "v": r["value"], "col": LEVEL_COLOR.get(r.get("level"), "#8a96a0")})
    rows = []
    for k, r in D["ranked"] + [(k, D["regs"][k]) for k in D["nodata"]]:
        rows.append({"k": k, "name": D["regs"][k]["name"] if lang == "ru" else REGION_EN[k], "v": r["value"],
                     "col": LEVEL_COLOR.get(r.get("level"), "#8a96a0"), "d": r.get("delta_1d")})
    P = {"total": total, "scenes": scenes, "cam": cam, "hz": {"px": hz[0], "py": hz[1]}, "events": evs,
         "labels": labels, "rows": rows, "U": U, "world": D["w"]["value"], "wcol": LEVEL_COLOR[D["w"]["level"]],
         "MW": MW, "MH": MH}
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    page = (tpl.replace("{{LANG}}", lang).replace("{{TOTAL}}", str(total)).replace("{{MAP_W}}", str(int(MW)))
            .replace("{{MAP_H}}", str(int(MH) + 1)).replace("{{PATHS}}", map_paths(D["idx"]))
            .replace("{{PLAN_JSON}}", json.dumps(P, ensure_ascii=False).replace("</", "<\\/")))
    (build / "index.html").write_text(page, encoding="utf-8")
    (build / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")
    sfx = [{"name": "impact", "t": 0.05}]
    for s in scenes[1:]:
        sfx.append({"name": "whoosh", "t": round(s["t0"] + 0.05, 2)})
    for s in scenes:
        if s["id"].startswith("ev"):
            sfx.append({"name": "click", "t": round(s["t0"] + 0.9, 2)})
    sfx.append({"name": "impact", "t": round(sc["outro"]["t0"] + 0.3, 2)})
    plan = {"date": date, "total": total, "sfx": sfx,
            "voice": [{"file": f"voice/{s['id']}.mp3", "t": s["voice_t"]} for s in scenes],
            "poster_t": 1.6, "texts": T, "ui": U}
    (build / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "description.txt").write_text(describe(lang, D, date), encoding="utf-8")
    (build / "narration.json").write_text(json.dumps(T, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"lang": lang, "total": total, "scenes": [(s["id"], s["t0"], s["t1"]) for s in scenes]}, ensure_ascii=False))


def regs_name(D, k, lang):
    return D["regs"][k]["name"] if lang == "ru" else REGION_EN[k]


# ───────────────────────── описание YouTube ─────────────────────────
def describe(lang, D, date):
    ru = lang == "ru"
    w, rk = D["w"], D["ranked"]
    v = w["value"]
    ds = fdate(D["data_date"], lang)
    if ru:
        title = f"Мир на уровне {v} из 100: индекс топливной напряжённости · {ds} #shorts"
        l = [title, "",
             f"Индекс топливной напряжённости (ИТН) на {ds}: мир — {v} из 100, уровень «{w['level_ru']}». "
             f"Регионы: " + "; ".join(f"{r['name']} — {r['value']}" for _, r in rk) + ".",
             "Что двигает индекс: Ормузский пролив "
             f"({fnum(D['hormuz']['now'], 'ru')} танкера в сутки при годовой медиане {fnum(D['hormuz']['med'], 'ru')}, {D['hormuz']['src']}, "
             f"{fdate(D['hormuz']['as_of'], 'ru')}) и розничные цены на дизель (США {fnum(D['us']['value'], 'ru', 2)} $/гал., "
             f"ЕС {round(D['eu']['value'])} €/1000 л — процентиль {D['pct']}+ к 5 годам).", "", "Свежие события:"]
        for e in D["events"]:
            l.append(f"— {fdate(e['occurred_at'], 'ru')}: {D['texts'][e['id']]['ru_card']} Источники: {src_names(e)}.")
        l += ["", f"Карта и методика: {SITE_URL}", f"Telegram-канал: {TG_URL}", "",
              "ОЦЕНКА: индекс рассчитан по открытым данным (OSINT), это не официальная информация; методика открыта.",
              "", "#ТопливныйФронт #нефть #дизель #Ормуз #энергетика #news"]
    else:
        title = f"World fuel tension at {v}/100: Fuel Tension Index · {ds} #shorts"
        l = [title, "",
             f"Fuel Tension Index (FTI) as of {ds}: the world is at {v} out of 100 ({LEVEL_EN[w['level']]}). "
             f"Regions: " + "; ".join(f"{REGION_EN[k]} {r['value']}" for k, r in rk) + ".",
             "What drives it: the Strait of Hormuz "
             f"({fnum(D['hormuz']['now'], 'en')} tankers a day vs a one-year median of {fnum(D['hormuz']['med'], 'en')}, {D['hormuz']['src']}, "
             f"{fdate(D['hormuz']['as_of'], 'en')}) and retail diesel prices (US ${fnum(D['us']['value'], 'en', 2)}/gal, "
             f"EU €{round(D['eu']['value'])}/1000 L; {D['pct']}th+ percentile vs five years).", "", "Latest events:"]
        for e in D["events"]:
            l.append(f"— {fdate(e['occurred_at'], 'en')}: {D['texts'][e['id']]['en_card']} Sources: {src_names(e)}.")
        l += ["", f"Map and methodology (site is in Russian): {SITE_URL}", f"Telegram: {TG_URL}", "",
              "ESTIMATE: the index is computed from open data (OSINT), not official data; the methodology is open.",
              "", "#FuelFront #oil #diesel #Hormuz #energy #news"]
    return "\n".join(l) + "\n"


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["compose"] and len(a) in (3, 4) and a[1] in ("ru", "en"):
        compose(a[1], Path(a[2]), a[3] if len(a) == 4 else None)
    else:
        sys.exit(__doc__)
