#!/usr/bin/env python3
"""Расчёт индекса топливного напряжения /lab/world (без LLM, детерминированно).

Читает data/world/series.json, пишет data/world/index.json и data/world/index-history.json.
Запуск:  python3 agents/world/index.py [--offline]
  --offline — явная отметка «только пересчёт из series.json». Скрипт и так ничего не качает
  (сбор — agents/world/collect.py), флаг оставлен для единообразия вызова.

Методика v0.2 (docs/world-lab-spec.md): пропущенный компонент НЕ перераспределяет вес:
value = Σ(score·w) / Σ(w доступных); coverage = Σ(w доступных); coverage < 0.5 -> value = null.
Устаревший (stale) или ошибочный без значения ряд выпадает из компонента.
"""
import argparse
import datetime as dt
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
D = os.path.join(ROOT, "data", "world")
SERIES = os.path.join(D, "series.json")
OUT = os.path.join(D, "index.json")
HIST = os.path.join(D, "index-history.json")
VERSION = "0.2"
BRAND = {"short": "FFI", "ru": "Индекс топливного фронта", "en": "Fuel Front Index"}
PRICE_YEARS = 10
MIN_COVERAGE = 0.5
CHOKE_FULL_DROP = 0.8
CHOKE_FULL_RISE = 0.5

REGIONS = {  # id: (название, вес в мировом индексе ~ доля потребления нефти)
    "north_america": ("Северная Америка", 0.24),
    "east_asia": ("Восточная Азия и АТР", 0.30),
    "europe": ("Европа", 0.15),
    "middle_east": ("Ближний Восток", 0.09),
    "south_asia": ("Южная Азия", 0.07),
    "latin_america": ("Латинская Америка", 0.07),
    "russia_cis": ("Россия и СНГ", 0.04),
    "africa": ("Африка", 0.04),
}
# v0.2: упор на региональные компоненты; общие для всех регионов (prices, diesel_crack, georisk) — 20% вместо 30%.
WEIGHTS = {"chokepoints": 0.30, "shortage_news": 0.15, "retail": 0.15, "stocks": 0.15, "prices": 0.10,
           "diesel_crack": 0.05, "georisk": 0.05, "phys_premium": 0.05}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
LABELS = {"chokepoints": "Узкие места (проливы)", "phys_premium": "Физическая премия",
          "prices": "Цены нефти и дизеля", "diesel_crack": "Дизельный крэк-спред",
          "retail": "Розничные цены на дизель", "stocks": "Запасы",
          "shortage_news": "Новости о дефиците топлива", "georisk": "Геополитический риск (GPR)"}
CHOKE = {  # пролив -> (подпись, регионы, инверсия: рост трафика = сигнал)
    "hormuz": ("Ормуз", ["middle_east", "south_asia", "east_asia"], False),
    "bab_el_mandeb": ("Баб-эль-Мандеб", ["europe", "middle_east"], False),
    "suez": ("Суэц", ["europe"], False),
    "malacca": ("Малакка", ["east_asia"], False),
    "bosporus": ("Босфор", ["europe", "russia_cis"], False),
    "cape": ("Мыс Доброй Надежды", ["africa"], True),
}
LEVELS = [(25, "calm", "спокойно"), (50, "tense", "напряжённо"), (75, "crisis", "кризис"),
          (101, "critical", "критично")]
TODAY = dt.date.today()


def level(v):
    if v is None:
        return None, "мало данных"
    for lim, k, ru in LEVELS:
        if v < lim:
            return k, ru
    return "critical", "критично"


def fmt(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def pct_mid(cur, vals):
    """Процентиль (mid-rank), 0..100."""
    if not vals:
        return None
    less = sum(1 for v in vals if v < cur)
    eq = sum(1 for v in vals if v == cur)
    return 100.0 * (less + 0.5 * eq) / len(vals)


def pct_low(cur, vals):
    """Процентиль, ничьи считаются «ниже» (для разреженных рядов с нулями: 0 -> score 0)."""
    if not vals:
        return None
    return 100.0 * sum(1 for v in vals if v < cur) / len(vals)


def pct_hist(cur, hist, years=PRICE_YEARS):
    """Процентиль к истории за years лет. Точки старше года — недельные средние (collect.py compact_weekly),
    поэтому весят ×5, чтобы недельная и дневная часть вносили вклад пропорционально календарному времени."""
    c1 = (TODAY - dt.timedelta(days=365)).isoformat()
    pts = [(d, v) for d, v in window(hist, years)]
    tot = less = eq = 0.0
    for d, v in pts:
        w = 1.0 if d >= c1 else 5.0
        tot += w
        if v < cur:
            less += w
        elif v == cur:
            eq += w
    return 100.0 * (less + 0.5 * eq) / tot if tot else None


def window(hist, years):
    c = (TODAY - dt.timedelta(days=int(365.25 * years))).isoformat()
    return [[d, v] for d, v in hist if d >= c]


def ma(hist, n=7):
    """Скользящее среднее по n последним календарным точкам (по записям, не по дням)."""
    vals = [v for _, v in hist]
    return [[hist[i][0], sum(vals[i - n + 1:i + 1]) / n] for i in range(n - 1, len(vals))]


def live(S, sid):
    """Ряд пригоден для расчёта: есть история, нет stale."""
    s = S.get(sid)
    if not s or s.get("stale") or not s.get("history"):
        return None
    return s


def absent(cid, why):
    return {"id": cid, "label": LABELS[cid], "score": None, "weight": WEIGHTS[cid], "raw": why,
            "as_of": None, "source": None, "available": False}


def comp(cid, score, raw, as_ofs, sources):
    return {"id": cid, "label": LABELS[cid], "score": round(max(0.0, min(100.0, score)), 1),
            "weight": WEIGHTS[cid], "raw": raw, "as_of": min(as_ofs),
            "source": ", ".join(sorted(set(sources))), "available": True}


# ---- вычисление компонентов (по данным, не зависящим от региона, кэшируется)
def choke_score(s, invert):
    h = s["history"]
    h365 = window(h, 1.0)
    if len(h365) < 120:
        return None
    med = statistics.median(v for _, v in h365)
    if med <= 0:
        return None
    m = ma(h365, 7)
    if len(m) < 60:
        return None
    cur = m[-1][1]
    # v0.2: линейная шкала, не процентиль. Отклонение трафика от медианы года: «падение» = 1 − ma7/медиана
    # (для Мыса Доброй Надежды знак обратный: рост = обход). 0% -> 0 баллов; падение на CHOKE_FULL_DROP (80%) и
    # глубже -> 100 (0 танкеров = 100); для Мыса рост на CHOKE_FULL_RISE (50%) -> 100. Нормальные колебания ±10% дают <13.
    dev = (cur / med - 1.0) if invert else (1.0 - cur / med)
    full = CHOKE_FULL_RISE if invert else CHOKE_FULL_DROP
    sc = 100.0 * max(0.0, min(1.0, dev / full))
    return sc, cur, med, s["as_of"]


def compute_common(S):
    C = {}
    # chokepoints
    for cid, (ru, regs, inv) in CHOKE.items():
        s = live(S, f"chokepoint_{cid}_tankers")
        r = choke_score(s, inv) if s else None
        if r:
            sc, cur, med, as_of = r
            word = "рост к медиане" if inv else "7-дн. среднее"
            C[("choke", cid)] = (sc, f"{ru}: {fmt(cur)} танк./сут. при медиане года {fmt(med)} ({word})", as_of, s["source"])
    # prices
    ps, raws, aos, srcs = [], [], [], []
    for sid, nm, unit in (("brent_spot", "Brent", "$/барр."), ("ulsd_nyh", "ULSD NYH", "$/гал.")):
        s = live(S, sid)
        if s:
            p = pct_hist(s["value"], s["history"])
            if p is not None:
                ps.append(p); raws.append(f"{nm} {fmt(s['value'], 2)} {unit} (p{p:.0f})")
                aos.append(s["as_of"]); srcs.append(s["source"])
    if ps:
        C["prices"] = (sum(ps) / len(ps), "; ".join(raws) + ", процентиль к 10 годам", aos, srcs)
    # crack
    b, u = live(S, "brent_spot"), live(S, "ulsd_nyh")
    if b and u:
        bm = dict(b["history"])
        cr = [[d, v * 42.0 - bm[d]] for d, v in u["history"] if d in bm]
        cr3 = window(cr, PRICE_YEARS)
        if len(cr3) > 100:
            cur = cr3[-1][1]
            p = pct_hist(cur, cr3)
            C["diesel_crack"] = (p, f"ULSD×42 − Brent = {fmt(cur)} $/барр. (p{p:.0f} к 10 годам)", [cr3[-1][0]],
                                 ["FRED / EIA"])
    # georisk
    g = live(S, "gpr_daily")
    if g:
        m = ma(window(g["history"], 5), 7)
        if len(m) > 200:
            cur = m[-1][1]
            p = pct_mid(cur, [v for _, v in m])
            C["georisk"] = (p, f"GPR (7-дн. среднее) {fmt(cur)}; p{p:.0f} к 5 годам", [g["as_of"]], [g["source"]])
    return C


def retail_for(S, region):
    sid, nm, unit = {"europe": ("eu_diesel_retail", "Дизель ЕС", "€/1000 л"),
                     "north_america": ("diesel_retail_us", "Дизель США", "$/гал.")}.get(region, (None,) * 3)
    s = live(S, sid) if sid else None
    if not s:
        return None
    h = [v for _, v in window(s["history"], 5)]
    p = pct_mid(s["value"], h)
    return p, f"{nm} {fmt(s['value'], 2 if unit != '€/1000 л' else 0)} {unit} (p{p:.0f} к 5 годам, номинал)", [s["as_of"]], [s["source"]]


def stocks_for(S, region):
    parts = []  # (score, raw, as_of, src)
    iea = {"europe": ("iea_stocks_days_europe", "IEA Европа"), "east_asia": ("iea_stocks_days_pacific", "IEA Азиатско-Тихоокеанский")}.get(region)
    if iea:
        s = live(S, iea[0])
        if s:
            h = [v for _, v in window(s["history"], 5)]
            p = pct_mid(s["value"], h)
            if p is not None and len(h) >= 12:
                parts.append((100 - p, f"{iea[1]}: {fmt(s['value'], 0)} дн. чист. импорта (p{p:.0f}; меньше = хуже)", s["as_of"], s["source"]))
    if region == "north_america":
        for sid, nm in (("us_crude_stocks", "сырая нефть"), ("us_distillate_stocks", "дистилляты")):
            s = live(S, sid)
            if s:
                h = [v for _, v in window(s["history"], 5)]
                p = pct_mid(s["value"], h)
                if p is not None and len(h) >= 52:
                    parts.append((100 - p, f"США {nm}: {fmt(s['value'], 0)} млн барр. (p{p:.0f}; меньше = хуже)", s["as_of"], s["source"]))
    if not parts:
        return None
    return (sum(p[0] for p in parts) / len(parts), "; ".join(p[1] for p in parts) + " (без сезонной поправки)",
            [p[2] for p in parts], [p[3] for p in parts])


def shortage_for(S, region):
    s = live(S, f"gdelt_shortage_{region}")
    if not s or len(s["history"]) < 30:
        return None
    m = ma(s["history"], 7)
    cur = m[-1][1]
    p = pct_low(cur, [v for _, v in m])
    return p, f"доля статей о дефиците топлива {fmt(cur, 4)}% (7-дн. среднее; p{p:.0f} к {len(m)} дн.)", [s["as_of"]], [s["source"]]


def build_region(S, C, region):
    comps = []
    # chokepoints
    items = [(cid, C[("choke", cid)]) for cid, (ru, regs, inv) in CHOKE.items()
             if region in regs and ("choke", cid) in C]
    if items:
        sc = max(x[1][0] for x in items)  # v0.2: берём худший пролив региона, а не среднее
        comps.append(comp("chokepoints", sc, "; ".join(x[1][1] for x in items), [x[1][2] for x in items],
                          [x[1][3] for x in items]))
    else:
        comps.append(absent("chokepoints", "нет контролируемых проливов в регионе или нет свежих данных"))
    comps.append(absent("phys_premium", "бесплатного ряда физической премии (фьючерс/спред) в v0.2 нет — компонент не подменяется"))

    def add(cid, r, why):
        if r:
            comps.append(comp(cid, r[0], r[1], r[2], r[3]))
        else:
            comps.append(absent(cid, why))
    add("prices", C.get("prices"), "нет свежих рядов цен")
    add("diesel_crack", C.get("diesel_crack"), "нет свежих рядов Brent/ULSD")
    add("retail", retail_for(S, region), "нет бесплатного ряда розничных цен для региона")
    add("stocks", stocks_for(S, region), "нет бесплатного ряда запасов для региона")
    add("shortage_news", shortage_for(S, region), "ряд GDELT недоступен или < 30 дней истории")
    add("georisk", C.get("georisk"), "нет ряда GPR")
    order = list(WEIGHTS)
    comps.sort(key=lambda c: order.index(c["id"]))
    av = [c for c in comps if c["available"]]
    cov = sum(c["weight"] for c in av)
    val = None
    if av and cov >= MIN_COVERAGE:
        val = sum(c["score"] * c["weight"] for c in av) / sum(c["weight"] for c in av)
    for c in comps:
        c.pop("available")
    return val, cov, comps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="только пересчёт из series.json (так и работает всегда)")
    ap.parse_args()
    S = json.load(open(SERIES, encoding="utf-8"))["series"]
    C = compute_common(S)

    try:
        hist = json.load(open(HIST, encoding="utf-8"))
        assert isinstance(hist, list)
    except Exception:
        hist = []
    today = TODAY.isoformat()
    prev = next((h for h in reversed(hist) if h["date"] < today), None)

    regions, rvals = {}, {}
    for rid, (name, w) in REGIONS.items():
        val, cov, comps = build_region(S, C, rid)
        v = None if val is None else round(val)
        k, ru = level(v)
        pv = prev["regions"].get(rid) if prev else None
        regions[rid] = {"name": name, "value": v, "level": k, "level_ru": ru,
                        "delta_1d": (v - pv) if (v is not None and pv is not None) else None,
                        "coverage": round(cov, 2), "weight_world": w, "components": comps}
        rvals[rid] = val

    av = {r: rvals[r] for r in rvals if rvals[r] is not None}
    wcov = sum(REGIONS[r][1] for r in av)
    wval = None
    if av and wcov >= MIN_COVERAGE:
        wval = sum(av[r] * REGIONS[r][1] for r in av) / wcov
    wv = None if wval is None else round(wval)
    k, ru = level(wv)
    pw = prev.get("world") if prev else None
    world = {"value": wv, "level": k, "level_ru": ru,
             "delta_1d": (wv - pw) if (wv is not None and pw is not None) else None,
             "coverage": round(wcov, 2),
             "regions_missing": [r for r in REGIONS if r not in av]}

    doc = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "methodology_version": VERSION, "brand": BRAND, "world": world, "regions": regions}

    entry = {"date": today, "world": wv, "regions": {r: regions[r]["value"] for r in REGIONS}}
    hist = [h for h in hist if h["date"] != today] + [entry]
    hist.sort(key=lambda h: h["date"])
    hist = hist[-800:]

    for path, data in ((OUT, doc), (HIST, hist)):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1 if path == OUT else None,
                      separators=None if path == OUT else (",", ":"))
        json.load(open(tmp, encoding="utf-8"))
        os.replace(tmp, path)

    print(f"world={wv} ({ru}) coverage={world['coverage']} Δ={world['delta_1d']}")
    for r, d in regions.items():
        print(f"  {r:14s} {d['value']!s:>4} {d['level_ru']:12s} cov={d['coverage']:.2f} "
              + " ".join(f"{c['id']}={c['score']}" for c in d["components"] if c["score"] is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
