#!/usr/bin/env python3
"""Недельный обзор «Топливный фронт РФ»: длинный ролик 16:9 (1920×1080) за 7 дней по окончанию --end-date.

  python3 weekly/build_weekly.py select  [--end-date D]            — что попадёт в обзор (без сети)
  python3 weekly/build_weekly.py prepare [--end-date D] [BUILD]     — кадры очевидцев + карта 16:9
  python3 weekly/build_weekly.py compose [--end-date D] [BUILD]     — озвучка, план, index.html, описание
  python3 weekly/build_weekly.py thumb   [--end-date D]             — обложка из out/weekly-<D>.mp4

Структура: хук (карта + итог недели) -> по дням: карточка дня, остановки камеры (объект, мощность и статус из
fuel-state, что произошло, уровень достоверности, кадры очевидцев до 5 с) -> баланс переработки -> статусы
заводов -> ссылка на полную карту. Слухи (rumored) не считаются и не показываются. Всё общее с рилсом
берётся из reel/build_reel.py (выбор, тексты, озвучка с кэшем, хэштеги).
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

os.environ["REEL_KIND"] = "weekly"          # build_reel читает режим при импорте: weekly — не urgent/evening
HERE = Path(__file__).resolve().parent
VIDEO = HERE.parent
sys.path.insert(0, str(VIDEO / "reel"))
import build_reel as R                      # noqa: E402
import fetch_clips as FC                    # noqa: E402
sys.path.insert(0, str(HERE))
import safety as SF                     # noqa: E402

B, G, N = R.B, R.G, R.N
R.VOICE_RATE = os.environ.get("WEEKLY_RATE", "+12%")   # обзор длиннее рилса: темп спокойнее
esc = R.esc
SITE = R.SITE_HOST
MAP_URL = f"https://{SITE}/?utm_source=youtube&utm_medium=weekly"

MAX_PER_DAY = int(os.environ.get("WEEKLY_PER_DAY", "5"))
MAX_TOTAL = float(os.environ.get("WEEKLY_MAX_SEC", "470"))
MIN_TOTAL = 180.0
CLIP_SHARE = 0.33          # кадры очевидцев — не больше трети ролика (по правилам канала)
CLIP_CAP = 4.5             # один фрагмент — не дольше 5 с
FLY, HOOK_MIN = 1.5, 9.5
WD = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WD_SHORT = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
MON_SHORT = ["", "ЯНВ", "ФЕВ", "МАР", "АПР", "МАЯ", "ИЮН", "ИЮЛ", "АВГ", "СЕН", "ОКТ", "НОЯ", "ДЕК"]
STATUS_RU = {"down": "остановлен", "partial": "частично", "operational": "работает"}
CONF_RU = {"confirmed": "ПОДТВЕРЖДЕНО", "reported": "СООБЩАЕТСЯ"}


# ───────────────────────────── даты ─────────────────────────────

def week_dates(end):
    e = dt.date.fromisoformat(end)
    return [(e - dt.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]


def dmy(date):          # 2026-10-04 -> (4, 10, 2026)
    y, m, d = (int(x) for x in date.split("-"))
    return d, m, y


def gen_ord(i):         # «четвёртое» -> «четвёртого»
    w = R.ORD[i]
    return w[:-2] + "ого" if w.endswith("ое") else (w[:-2] + "его" if w.endswith("ье") else w)


def range_label(dates):  # «4–10 октября» | «30 сентября – 6 октября»
    (d1, m1, _), (d2, m2, _) = dmy(dates[0]), dmy(dates[-1])
    if m1 == m2:
        return f"{d1}–{d2} {R.MONTHS[m2]}"
    return f"{d1} {R.MONTHS[m1]} – {d2} {R.MONTHS[m2]}"


def range_voice(dates):
    (d1, m1, _), (d2, m2, _) = dmy(dates[0]), dmy(dates[-1])
    a = f"С {gen_ord(d1)}" + ("" if m1 == m2 else f" {R.MONTHS[m1]}")
    return f"{a} по {R.ORD[d2]} {R.MONTHS[m2]}"


def mmss(t):
    t = int(round(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def plural(n, a, b, c):
    return G.plural(n, a, b, c)


def default_end():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date().isoformat()   # МСК: cron в воскресенье = конец недели


# ───────────────────────────── выбор ─────────────────────────────

def load_week(end):
    """-> (week, stops, info). week — подтверждённые/сообщаемые удары окна; слухи не входят."""
    dates = week_dates(end)
    data = json.loads((R.ROOT / "data" / "strikes.json").read_text(encoding="utf-8"))
    arr = data.get("strikes", data) if isinstance(data, dict) else data
    fuel = json.loads((R.ROOT / "data" / "fuel-state.json").read_text(encoding="utf-8"))
    refs = fuel.get("refineries", [])
    week, seen, rumored = [], set(), 0
    for raw in arr:
        d = str(raw.get("date", ""))[:10]
        if d not in dates:
            continue
        sid = R.strike_id(raw)
        if sid in seen:
            continue
        seen.add(sid)
        s = G.normalize_strike(raw)
        s["_sid"], s["date"] = sid, d
        if str(s.get("confidence", "reported")).lower() not in ("confirmed", "reported"):
            rumored += 1
            continue
        ll = R.locate(s, refs, arr)
        s["lat"], s["lon"] = (ll if ll else (None, None))
        s["cls"] = R.strike_class(s)
        week.append(s)
    stops = []
    for di, d in enumerate(dates):
        pool = [s for s in week if s["date"] == d and s["lat"] is not None]
        pool.sort(key=lambda s: (s["cls"], G.strike_rank(s)), reverse=True)
        groups, by_city = [], {}
        for s in pool:
            c = str(s.get("city") or s.get("region") or "").strip().lower()
            if c in by_city:
                by_city[c]["_group"].append(s)
                continue
            s["_group"] = [s]
            by_city[c] = s
            groups.append(s)
        top = [g for g in groups if g["cls"] == 2][:MAX_PER_DAY]
        if len(top) < 3:
            top += [g for g in groups if g not in top][:3 - len(top)]
        for g in top:
            g["_di"] = di
            g["_prio"] = (g["cls"], G.strike_rank(g))
            stops.append(g)
    info = {"end": end, "dates": dates, "N": len(week), "M": sum(1 for s in week if s["cls"] == 2),
            "rumored": rumored, "refs": refs, "fuel": fuel,
            "per_day": {d: {"n": sum(1 for s in week if s["date"] == d),
                            "m": sum(1 for s in week if s["date"] == d and s["cls"] == 2)} for d in dates}}
    return week, stops, info


def refinery_of(s, refs):
    text = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    for rx, r in B.refinery_matchers(refs):
        if rx.search(text):
            return r
    return None


def cmd_select(end):
    week, stops, info = load_week(end)
    print(f"неделя {info['dates'][0]}…{end}: ударов {info['N']} (по НПЗ/энергетике {info['M']}), слухов исключено {info['rumored']}, остановок {len(stops)}")
    for d in info["dates"]:
        print(f"  {d}: {info['per_day'][d]}")
    for s in stops:
        print(f"  {s['date']} cls{s['cls']} {s.get('city')} | {R.object_name(s, info['refs'])} | {s.get('confidence')} | в группе {len(s['_group'])}")


# ───────────────────────────── prepare ─────────────────────────────

def vet_clip(c, build):
    """True — на кадрах нет людей и пострадавших. Нет ответа модели -> False (клип не берём)."""
    cache = build / "vet.json"
    vet = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    key = c["file"]
    if key in vet:
        return vet[key]
    src = build / "assets" / c["file"]
    tile = build / "assets" / f"_vet-{hashlib.md5(key.encode()).hexdigest()[:8]}.jpg"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf",
                        "fps=1/1.2,scale=360:-2,tile=3x1", "-frames:v", "1", "-q:v", "3", str(tile)])
    ok = None
    if r.returncode == 0 and tile.exists():
        prompt = (f"Открой изображение {tile} инструментом Read. Это три кадра подряд из видео очевидцев удара по "
                  "объекту в России. Определи, есть ли на любом кадре люди (даже издали, силуэты), тела, пострадавшие "
                  'или кровь. Ответь СТРОГО одним JSON: {"people": true|false}.')
        for _ in range(3):
            try:
                o = subprocess.run(["claude-run", "-p", prompt, "--model", R.HAIKU, "--effort", "high",
                                    "--allowedTools", "Read"], capture_output=True, text=True, timeout=180,
                                   stdin=subprocess.DEVNULL)
                m = re.search(r'"people"\s*:\s*(true|false)', o.stdout)
                if m:
                    ok = m.group(1) == "false"
                    break
            except (subprocess.TimeoutExpired, OSError):
                pass
    tile.unlink(missing_ok=True)
    if ok is None:
        print(f"weekly: проверка кадров {key} не получена — клип не берём", file=sys.stderr)
        return False        # без проверки на людей кадры не показываем
    vet[key] = ok
    cache.write_text(json.dumps(vet), encoding="utf-8")
    if not ok:
        print(f"weekly: на кадрах {key} люди — клип не берём", file=sys.stderr)
    return ok


def cmd_prepare(end, build):
    week, stops, info = load_week(end)
    if not stops:
        print(f"weekly: за неделю по {end} нет ударов с координатами", file=sys.stderr)
        sys.exit(4)
    build.mkdir(parents=True, exist_ok=True)
    (build / "assets").mkdir(exist_ok=True)
    clips = []
    for s in stops:
        c = None
        if s["cls"] == 2 and os.environ.get("WEEKLY_CLIPS", "1") != "0":
            try:
                c = FC.fetch_for(s, build / "assets")
            except Exception as e:  # noqa: BLE001
                print(f"weekly: кадры для {s.get('city')} не получены ({e})", file=sys.stderr)
        if c and (c.get("kind") != "video" or not vet_clip(c, build)):
            c = None
        clips.append(c)
    used, seen = [], set()
    for c in clips:                     # один кадр = один удар
        key = (c or {}).get("src")
        used.append(None if (c and key in seen) else c)
        seen.add(key)
    clips = used
    marks = [{"sid": s["_sid"], "date": s["date"], "lat": s["lat"], "lon": s["lon"]} for s in week if s["lat"] is not None]
    snap = {"info": {k: v for k, v in info.items() if k not in ("refs", "fuel")}, "marks": marks,
            "stops": [{**{k: v for k, v in s.items() if not k.startswith("_g")},
                       "_group": [{k: v for k, v in x.items() if k != "_group"} for x in s["_group"]]} for s in stops]}
    (build / "week.json").write_text(json.dumps(snap, ensure_ascii=False, default=str), encoding="utf-8")
    (build / "clips.json").write_text(json.dumps(clips, ensure_ascii=False), encoding="utf-8")
    pts = [{"id": f"m{j}", "lat": m["lat"], "lon": m["lon"]} for j, m in enumerate(marks)]
    lats, lons = [p["lat"] for p in pts], [p["lon"] for p in pts]
    pl, po = (max(lats) - min(lats)) * 0.2 + 2.5, (max(lons) - min(lons)) * 0.2 + 3.0
    lo_lon, hi_lon = min(lons) - po, max(lons) + po
    if hi_lon - lo_lon < 24:
        c0 = (lo_lon + hi_lon) / 2
        lo_lon, hi_lon = c0 - 12, c0 + 12
    targets = {"bounds": [[min(lats) - pl, lo_lon], [max(lats) + pl, hi_lon]], "points": pts, "url": f"https://{SITE}/"}
    (build / "targets.json").write_text(json.dumps(targets), encoding="utf-8")
    env = {**os.environ, "CAP_W": "3840", "CAP_H": "2160", "CAP_DPR": "1.5"}
    subprocess.run(["node", str(R.REEL / "capture_map.mjs"), str(build / "targets.json"),
                    str(build / "assets" / "map.jpg"), str(build / "map-points.json")],
                   check=True, timeout=300, cwd=str(VIDEO), env=env)
    print(json.dumps([{"city": s.get("city"), "clip": c and c["src"]} for s, c in zip(stops, clips)], ensure_ascii=False))


# ───────────────────────────── тексты ─────────────────────────────

def num_ru(x):
    return f"{x:.1f}".replace(".", ",").replace(",0", "") if isinstance(x, float) else str(x)


def mt_words(x):        # 20.1 -> «20,1 миллиона», 12 -> «12 миллионов»
    if abs(x - round(x)) > 0.049:
        return f"{num_ru(round(x, 1))} миллиона"
    n = int(round(x))
    return f"{n} {plural(n, 'миллион', 'миллиона', 'миллионов')}"


def stop_voice(s, refs, line):
    """Реплика Haiku/шаблон + факты из fuel-state — числа и статус всегда скриптом."""
    line = line.rstrip(".")
    if SF.is_crimea(s):       # нейтральная пометка источника (решение владельца 10.10.2026)
        line = re.sub(r"^([^:]{1,40}):", lambda m: m.group(1) + (", Крым" if "Крым" not in m.group(1) else "") +
                      ", " + SF.CRIMEA_NOTE + ":", line, count=1)
    parts = [line + "."]
    r = refinery_of(s, refs)
    if r and r.get("capacity_mt_year"):
        st = {"down": "остановлен", "partial": "работает частично", "operational": "работает"}.get(r.get("status"), "")
        cap = float(r["capacity_mt_year"])
        parts.append((f"По оценке карты, завод {st}; " if st else "Завод: ") + f"мощность {mt_words(cap)} тонн в год.")
    k = len(s.get("_group", []))
    if k > 1:
        parts.append(f"Всего по городу за день {k} {plural(k, 'удар', 'удара', 'ударов')}.")
    return " ".join(parts)


def narr_lines(stops, refs, build):
    """Реплика на остановку: кэш build/narration.json по sid, недостающие — Haiku одной пачкой."""
    cache = build / "narration.json"
    per = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    todo = [s for s in stops if s["_sid"] not in per]
    if todo:
        got = R.llm_lines(todo, refs) or [R.strike_template(s, refs) for s in todo]
        for s, x in zip(todo, got):
            per[s["_sid"]] = x
        cache.write_text(json.dumps(per, ensure_ascii=False, indent=1), encoding="utf-8")
    return {s["_sid"]: clean_line(s, per[s["_sid"]], refs) for s in stops}


def clean_line(s, line, refs):
    """Реплика без упоминаний погибших/раненых: вырезаем обороты; не осталось смысла — шаблон, затем минимум."""
    x = SF.scrub(line, head=True) or SF.scrub(R.strike_template(s, refs), head=True)
    if not x:
        place = str(s.get("city") or s.get("region") or "").strip()
        x = f"{place}: удар по объекту {R.object_name(s, refs)}."
    return x


def clean_what(s, refs):
    """R.what_happened без людских потерь; запасной — нейтральная фраза про объект."""
    wh = SF.scrub(R.what_happened(s), whole_sentence=True) or f"Сообщается об атаке БПЛА. Объект: {R.object_name(s, refs)}."
    if SF.is_crimea(s):
        wh += f" Крым — {SF.CRIMEA_NOTE}."
    return wh


def sub_chunks(text, t0, dur, limit=88):
    """Субтитры: предложения, длинные режем по запятой; время — пропорционально числу знаков."""
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
    out = []
    for x in sents:
        while len(x) > limit:
            cut = x.rfind(", ", 30, limit)
            cut = cut + 1 if cut > 0 else x.rfind(" ", 30, limit)
            out.append(x[:cut].strip())
            x = x[cut:].strip(" ,")
        out.append(x)
    total = sum(len(x) for x in out) or 1
    subs, t = [], t0
    for x in out:
        d = dur * len(x) / total
        subs.append({"t0": round(t, 2), "t1": round(t + d, 2), "text": x})
        t += d
    return subs


# ───────────────────────────── compose ─────────────────────────────

def compose(end, build):
    week, stops, info = load_week(end)
    snap = json.loads((build / "week.json").read_text(encoding="utf-8"))
    # состав берём из снимка prepare: кадры и карта сняты именно под него
    by_sid = {s["_sid"]: s for s in stops}
    stops2 = []
    for sd in snap["stops"]:
        g = sd.pop("_group")
        sd["_group"] = g
        sd["_prio"] = (sd.get("cls", 0), G.strike_rank(sd))
        stops2.append(sd)
    stops = stops2
    for s in stops:
        s["_di"] = info["dates"].index(s["date"])
    clips = json.loads((build / "clips.json").read_text(encoding="utf-8"))
    seen_src = set()
    for i, c in enumerate(clips):      # один пост очевидцев = один удар (две записи по одной ЛПДС)
        if c and c["src"] in seen_src:
            clips[i] = None
        elif c:
            seen_src.add(c["src"])
    refs, fuel = info["refs"], info["fuel"]
    dates = info["dates"]
    mp = json.loads((build / "map-points.json").read_text(encoding="utf-8"))
    P = {p["id"]: p for p in mp["points"]}
    IW, IH = mp["w"], mp["h"]
    S0 = 1920 / IW
    SZ = S0 * float(os.environ.get("WEEKLY_ZOOM", "4.0"))
    marks_src = snap["marks"]
    n_all, m_all = snap["info"]["N"], snap["info"]["M"]
    info.update({k: snap["info"][k] for k in ("N", "M", "per_day", "rumored")})

    # ── озвучка ──
    (build / "voice").mkdir(exist_ok=True)
    nb = fuel.get("national_balance", {})
    per = narr_lines(stops, refs, build)
    texts = {}
    hook = f"{range_voice(dates)}: {n_all} {plural(n_all, 'удар', 'удара', 'ударов')} по России"
    hook += (f", из них {m_all} — по НПЗ и энергетике" if m_all else "") + ". По данным открытых источников."
    texts["hook"] = hook
    for di, d in enumerate(dates):
        pd = info["per_day"][d]
        if not pd["n"]:
            continue
        dd, mm, _ = dmy(d)
        t = f"{R.ORD[dd].capitalize()} {R.MONTHS[mm]}, {WD[dt.date.fromisoformat(d).weekday()]}. {pd['n']} {plural(pd['n'], 'удар', 'удара', 'ударов')}"
        texts[f"d{di}"] = t + (f", из них {pd['m']} — по топливу и энергетике." if pd["m"] else ".")
    for i, s in enumerate(stops):
        texts[f"s{i}"] = stop_voice(s, refs, per[s["_sid"]])
    cap_total, cap_off = nb.get("refining_capacity_total_mt_year"), nb.get("capacity_offline_mt_year")
    pct, gl, dl = nb.get("capacity_offline_pct"), nb.get("gasoline_output_loss_pct"), nb.get("diesel_output_loss_pct")
    have_bal = all(isinstance(x, (int, float)) for x in (cap_total, cap_off, pct))
    if have_bal:
        t = (f"Баланс переработки по оценке карты. Из {num_ru(float(cap_total))} миллионов тонн годовых мощностей "
             f"остановлено {num_ru(float(cap_off))}, это {int(round(pct))} процентов.")
        if isinstance(gl, (int, float)) and isinstance(dl, (int, float)):
            t += f" Выпуск бензина ниже на {int(round(gl))} процентов, дизеля — на {int(round(dl))}."
        texts["bal"] = t
    start, endd = dates[0], dates[-1]
    changed = sorted([r for r in refs if r.get("status") in ("down", "partial") and str(r.get("status_since") or "") >= start
                      and str(r.get("status_since") or "") <= endd], key=lambda r: -(r.get("capacity_mt_year") or 0))[:6]
    if changed:
        names = [r["name"] for r in changed[:5]]
        texts["tab"] = ("Заводы, у которых за неделю изменился статус на карте: " + ", ".join(names[:-1]) +
                        (" и " if len(names) > 1 else "") + names[-1] + ".")
    texts["cta"] = "Полная карта всех ударов — по ссылке в описании. Это оценка по открытым источникам, а не официальные данные."
    (build / "texts.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1), encoding="utf-8")
    leak = [k for k, t in texts.items() if SF.has_casualty(t)]
    if leak:
        raise SystemExit(f"weekly: в озвучке остались упоминания потерь {leak} — правьте safety.py")
    vo = R.tts_all(list(texts.items()), build / "voice")     # каскад edge -> gemini -> edge2 -> piper
    failed = [k for k in texts if k not in vo]
    if failed:
        print(f"weekly: голос не получен для {failed} — повторите сборку позже (удачные фразы в кэше)", file=sys.stderr)
        sys.exit(5)

    # ── таймлайн (с подгонкой под бюджет) ──
    def timeline(keep, use_clips):
        T, segs, cam, subs, voice, sfx, cl = 0.0, [], [], [], [], [], []
        ov = {"x": IW / 2, "y": IH / 2, "s": S0 * 1.05, "ax": 1040, "ay": 540}
        hold = lambda t, p: cam.append({"t": round(t, 2), **p, "dip": 0})
        arrive_to = lambda t, p, dip=0.25: cam.append({"t": round(t, 2), **p, "dip": dip})
        hook_end = max(HOOK_MIN, vo["hook"][1] + 0.9)
        hold(0, {**ov, "s": S0 * 1.18})
        arrive_to(hook_end, ov, 0.0)
        segs.append({"type": "hook", "id": "c_hook", "t0": 0, "t1": round(hook_end, 2), "pill": "", "di": -1})
        voice.append({"file": vo["hook"][0], "t": 0.4})
        subs += sub_chunks(texts["hook"], 0.4, vo["hook"][1])
        sfx += [("impact", 0.05)]
        T = hook_end
        chapters = [(0.0, "Итог недели")]
        pos = ov
        marks_day = {}
        for di, d in enumerate(dates):
            ds = [i for i in keep if stops[i]["_di"] == di]
            if not ds and not info["per_day"][d]["n"]:
                continue
            if f"d{di}" in vo:
                dur = max(3.4, vo[f"d{di}"][1] + 0.9)
                segs.append({"type": "day", "id": f"c_day{di}", "t0": round(T, 2), "t1": round(T + dur, 2),
                             "pill": f"dp{di}", "di": di})
                arrive_to(T + 1.1, ov, 0.2)
                hold(T + dur, ov)
                voice.append({"file": vo[f"d{di}"][0], "t": round(T + 0.5, 2)})
                subs += sub_chunks(texts[f"d{di}"], T + 0.5, vo[f"d{di}"][1])
                sfx += [("whoosh", T + 0.1), ("impact", T + 0.45)]
                dd, mm, _ = dmy(d)
                chapters.append((T, f"{dd} {R.MONTHS[mm]}, {WD[dt.date.fromisoformat(d).weekday()]}"))
                T += dur
            for i in ds:
                s = stops[i]
                mj = next(j for j, m in enumerate(marks_src) if m["sid"] == s["_sid"])
                p = P[f"m{mj}"]
                tgt = {"x": p["x"], "y": p["y"], "s": SZ, "ax": 1240, "ay": 330}
                t0, arrive = T, T + FLY
                vs = arrive + 0.25
                vend = vs + vo[f"s{i}"][1]
                c = use_clips[i]
                v0 = v1 = None
                if c:
                    v0 = arrive + 1.7
                    v1 = v0 + min(c["dur"], CLIP_CAP)
                t1 = max(vend + 0.5, (v1 + 0.4) if v1 else 0, arrive + 3.0)
                segs.append({"type": "stop", "id": f"st{i}", "t0": round(t0, 2), "t1": round(t1, 2), "arrive": round(arrive, 2),
                             "m": mj, "pill": f"dp{di}", "di": di})
                arrive_to(arrive, tgt, 0.3)
                hold(t1, tgt)
                voice.append({"file": vo[f"s{i}"][0], "t": round(vs, 2)})
                subs += sub_chunks(texts[f"s{i}"], vs, vo[f"s{i}"][1])
                sfx += [("whoosh", t0 + 0.1), ("click", arrive + 0.05)]
                if c:
                    cl.append({"id": f"fw{i}", "i": i, "v0": round(v0, 2), "v1": round(v1, 2), "file": c["file"], "src": c["src"]})
                    sfx.append(("click", v0))
                marks_day[mj] = di
                T = t1
        # итоговые слайды
        for k, title in (("bal", "Баланс переработки"), ("tab", "Статусы заводов"), ("cta", "Полная карта")):
            if k not in vo:
                continue
            dur = max(7.0 if k != "cta" else 7.5, vo[k][1] + 1.2)
            segs.append({"type": k, "id": f"s_{k}", "t0": round(T, 2), "t1": round(T + dur, 2), "pill": "", "di": -1})
            arrive_to(T + 0.8, ov, 0.15)
            hold(T + dur, ov)
            voice.append({"file": vo[k][0], "t": round(T + 0.5, 2)})
            subs += sub_chunks(texts[k], T + 0.5, vo[k][1])
            sfx += [("whoosh", T + 0.1)]
            chapters.append((T, title))
            T += dur
        return {"total": round(T + 0.4, 2), "segs": segs, "cam": cam, "subs": subs, "voice": voice, "sfx": sfx,
                "clips": cl, "hook_end": hook_end, "chapters": chapters}

    keep = list(range(len(stops)))
    use_clips = list(clips)
    tl = timeline(keep, use_clips)
    def share(t):
        return sum(c["v1"] - c["v0"] for c in t["clips"]) / t["total"]
    guard = 0
    while (tl["total"] > MAX_TOTAL or share(tl) > CLIP_SHARE) and guard < 200:
        guard += 1
        if share(tl) > CLIP_SHARE:           # сначала кадры у наименее важных остановок
            cand = [i for i in keep if use_clips[i]]
            use_clips[min(cand, key=lambda i: stops[i]["_prio"])] = None
        else:                                # потом сами остановки (минимум одна на день)
            per_day = {}
            for i in keep:
                per_day.setdefault(stops[i]["_di"], []).append(i)
            cand = [i for lst in per_day.values() if len(lst) > 1 for i in lst]
            if not cand:
                break
            keep.remove(min(cand, key=lambda i: stops[i]["_prio"]))
        tl = timeline(keep, use_clips)
    total = tl["total"]
    kept_clips = sum(1 for i in keep if use_clips[i])
    print(f"weekly: остановок {len(keep)}/{len(stops)}, кадров {kept_clips}, длительность {total:.0f} с, доля кадров {share(tl) * 100:.0f}%")

    # ── метки на карте ──
    marks, sel_ids = [], {stops[i]["_sid"] for i in keep}
    stop_mark = {}
    for j, m in enumerate(marks_src):
        p = P[f"m{j}"]
        di = dates.index(m["date"])
        marks.append({"x": p["x"], "y": p["y"], "day": di, "on": round(0.6 + di * 0.95 + (j % 5) * 0.06, 2),
                      "sel": m["sid"] in sel_ids})
    for sg in tl["segs"]:
        if sg["type"] == "stop":
            marks[sg["m"]]["on"] = min(marks[sg["m"]]["on"], 6.5)

    # ── HTML ──
    def stop_card(i):
        s = stops[i]
        r = refinery_of(s, refs)
        conf = str(s.get("confidence", "reported")).lower()
        wh = clean_what(s, refs)
        if N and N.text_reasons(wh):
            wh = per[s["_sid"]]
        cap = ""
        if r and r.get("capacity_mt_year"):
            cap = (f'<span class="lb">МОЩНОСТЬ</span><b>{num_ru(float(r["capacity_mt_year"]))}</b><span class="u">млн т/год</span>'
                   f'<span class="lb">СТАТУС (ОЦЕНКА)</span><span class="st {esc(r.get("status", "operational"))}">'
                   f'{STATUS_RU.get(r.get("status"), "")}</span>')
        else:
            cap = f'<span class="lb">ТИП ОБЪЕКТА</span><b>{esc(R.kind_label(s))}</b>'
        dd, mm, _ = dmy(s["date"])
        return (f'<div class="card paper" id="st{i}"><div class="c-row"><span class="c-k {"k1" if conf == "reported" else ""}">'
                f'{CONF_RU.get(conf, "СООБЩАЕТСЯ")}</span><span class="c-d">{dd:02d}.{mm:02d} · {WD_SHORT[dt.date.fromisoformat(s["date"]).weekday()]}</span></div>'
                f'<div class="c-city">{esc(s.get("city") or s.get("region") or "")}</div>'
                f'<div class="c-obj">{esc(R.object_name(s, refs))}</div><div class="c-cap">{cap}</div>'
                f'<div class="c-txt">{esc(wh)}</div></div>')

    cards = [f'<div class="card glass" id="c_hook"><div class="gk">НЕДЕЛЯ {esc(range_label(dates).upper())}</div>'
             f'<div class="hbig">{n_all}</div><div class="hw">{plural(n_all, "удар", "удара", "ударов")} по России</div>'
             + (f'<div class="hrow"><b>{m_all}</b><span>по НПЗ и энергетике</span></div>' if m_all else "")
             + '<div class="hdt">ОЦЕНКА ПО ОТКРЫТЫМ ИСТОЧНИКАМ</div></div>']
    for di, d in enumerate(dates):
        if f"d{di}" not in vo:
            continue
        pd = info["per_day"][d]
        dd, mm, _ = dmy(d)
        cards.append(f'<div class="card glass" id="c_day{di}"><div class="gk">ДЕНЬ {di + 1} ИЗ 7</div>'
                     f'<div class="dwd">{WD[dt.date.fromisoformat(d).weekday()].capitalize()}</div>'
                     f'<div class="ddt">{dd} {R.MONTHS[mm]}</div>'
                     f'<div class="hrow"><b>{pd["n"]}</b><span>{plural(pd["n"], "удар", "удара", "ударов")} за день</span></div>'
                     + (f'<div class="hdt">ПО НПЗ И ЭНЕРГЕТИКЕ — {pd["m"]}</div>' if pd["m"] else "") + '</div>')
    cards += [stop_card(i) for i in keep]
    videos, shown_src = [], []
    for c in tl["clips"]:
        src_txt = re.sub(r"^https?://", "", c["src"])
        shown_src.append(c["src"])
        videos.append(f'<div class="fw" id="{c["id"]}"><video id="v{c["i"]}" class="clip" src="assets/{esc(c["file"])}" muted playsinline '
                      f'data-start="{c["v0"]}" data-duration="{round(c["v1"] - c["v0"] + 0.35, 2)}" data-track-index="{100 + c["i"]}"></video>'
                      f'<div class="src"><span>Кадры очевидцев · источник</span><b>{esc(src_txt)}</b></div></div>')
    slides = []
    if have_bal:
        flags = []
        if nb.get("export_ban_gasoline"): flags.append("Запрет экспорта бензина")
        if nb.get("export_ban_kerosene"): flags.append("Запрет экспорта керосина")
        if nb.get("import_from_belarus"): flags.append("Импорт из Беларуси")
        bars = [("Мощности остановлены", pct), ("Выпуск бензина ниже на", gl), ("Выпуск дизеля ниже на", dl)]
        bars_html = "".join(f'<div class="bar"><div class="bl">{lb}</div><div class="bt"><div class="bf{" a" if j else ""}" data-w="{v}"></div></div>'
                            f'<div class="bv">{int(round(v))}%</div></div>' for j, (lb, v) in enumerate(bars) if isinstance(v, (int, float)))
        slides.append(f'<div class="slide" id="s_bal"><div class="sl-k">БАЛАНС ПЕРЕРАБОТКИ · ОЦЕНКА КАРТЫ</div>'
                      f'<div class="sl-big">{int(round(pct))}<i>%</i></div><div class="sl-cap">мощностей НПЗ остановлено</div>'
                      f'<div class="sl-cap" style="font-size:36px;color:#9fb6c1;font-weight:600">{num_ru(float(cap_off))} из {num_ru(float(cap_total))} млн т в год</div>'
                      f'<div class="bars">{bars_html}</div>'
                      f'<div class="flags">{"".join(f"<span>{x}</span>" for x in flags)}</div>'
                      f'<div class="sl-src">Данные карты на {esc(R.G.rus_date(str(fuel.get("meta", {}).get("generated_at", end))[:10]))} · оценка по открытым источникам</div></div>')
    if changed:
        rows = "".join(f'<tr><td class="n">{esc(r["name"])}</td><td>{esc(r.get("region", ""))}</td>'
                       f'<td class="m">{num_ru(float(r.get("capacity_mt_year") or 0))}</td>'
                       f'<td><span class="chip {esc(r["status"])}">{STATUS_RU.get(r["status"], "")}</span></td>'
                       f'<td class="m">{str(r["status_since"])[8:10]}.{str(r["status_since"])[5:7]}</td></tr>' for r in changed)
        slides.append('<div class="slide" id="s_tab"><div class="sl-k">СТАТУСЫ ЗАВОДОВ ЗА НЕДЕЛЮ · ОЦЕНКА КАРТЫ</div>'
                      '<table class="tab"><thead><tr><th>ЗАВОД</th><th>РЕГИОН</th><th>МОЩНОСТЬ, МЛН Т/ГОД</th><th>СТАТУС</th><th>С</th></tr></thead>'
                      f'<tbody>{rows}</tbody></table></div>')
    slides.append('<div class="slide" id="s_cta"><div class="sl-k">ПОЛНАЯ КАРТА</div>'
                  '<div class="cta-big">Все удары, заводы и баланс — на карте</div>'
                  f'<div class="cta-url">{SITE}</div><div class="cta-tg">Telegram: <span>{R.TG_HANDLE}</span></div>'
                  '<div class="cta-w">Ссылка — в описании. <b>ОЦЕНКА:</b> агрегация открытых источников (OSINT), не официальные данные. '
                  'Слухи в обзор не включены.</div></div>')
    pills = "".join(f'<div class="dp" id="dp{di}">{WD_SHORT[dt.date.fromisoformat(d).weekday()]} · {dmy(d)[0]} {MON_SHORT[dmy(d)[1]]}</div>'
                    for di, d in enumerate(dates))

    plan = {"S0": S0, "SZ": SZ, "total": total, "hook_end": tl["hook_end"], "cam": tl["cam"], "segs": tl["segs"],
            "marks": marks, "clips": [{"id": c["id"], "v0": c["v0"], "v1": c["v1"]} for c in tl["clips"]], "subs": tl["subs"]}
    for sg in plan["segs"]:
        sg.setdefault("d0", 0)
    (build / "assets").mkdir(exist_ok=True)
    (build / "assets" / "plan.js").write_text("window.PLAN = " + json.dumps(plan, ensure_ascii=False) + ";\n", encoding="utf-8")
    for f in ("fonts",):
        shutil.copytree(VIDEO / "template" / "assets" / f, build / "assets" / f, dirs_exist_ok=True)
    shutil.copy2(VIDEO / "node_modules" / "gsap" / "dist" / "gsap.min.js", build / "assets" / "gsap.min.js")
    subs = {"LANG": "ru", "IW": IW, "IH": IH, "TOTAL": total, "VIDEOS": "\n".join(videos), "CARDS": "\n".join(cards),
            "SLIDES": "\n".join(slides), "PILLS": pills, "BRAND": "ТОПЛИВНЫЙ ФРОНТ РФ", "SITE": SITE,
            "FOOT_L": esc(f"ОЦЕНКА ПО ОТКРЫТЫМ ИСТОЧНИКАМ · {range_label(dates).upper()} {dmy(dates[-1])[2]}")}
    page = (HERE / "template" / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: str(subs[m.group(1)]), page)
    (build / "index.html").write_text(page, encoding="utf-8")
    (build / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")
    mixplan = {"date": end, "total": total, "n_strikes": len(keep),
               "sfx": [{"name": a, "t": round(max(0, x), 2)} for a, x in tl["sfx"]], "voice": tl["voice"]}
    (build / "plan.json").write_text(json.dumps(mixplan, ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "objects.json").write_text(json.dumps({
        "N": n_all, "M": m_all, "dates": dates, "range": range_label(dates), "end": end,
        "bal": {"total": cap_total, "offline": cap_off, "pct": pct} if have_bal else None,
        "objects": [{"city": stops[i].get("city") or stops[i].get("region") or "", "object": R.object_name(stops[i], refs),
                     "what": clean_what(stops[i], refs), "date": stops[i]["date"]} for i in keep]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "chapters.json").write_text(json.dumps(tl["chapters"], ensure_ascii=False), encoding="utf-8")
    (build / "description.txt").write_text(describe(end, info, [stops[i] for i in keep], tl["chapters"], shown_src, changed, nb, have_bal),
                                           encoding="utf-8")
    print(json.dumps({"end": end, "total": total, "stops": [stops[i].get("city") for i in keep]}, ensure_ascii=False))


# ───────────────────────────── описание ─────────────────────────────

def describe(end, info, sel, chapters, src, changed, nb, have_bal):
    dates = info["dates"]
    rng = range_label(dates)
    n, m = info["N"], info["M"]
    title = f"Удары по НПЗ России за неделю {rng}: итоги, карта, баланс"
    lines = [title, "",
             f"Итоги недели {rng}: {n} {plural(n, 'удар', 'удара', 'ударов')} по России" + (f", из них {m} — по НПЗ и энергетике." if m else ".")
             + " Обзор по открытым источникам (OSINT): объекты, мощности и статусы заводов на карте сайта.", "",
             "Главы:"]
    lines += [f"{mmss(t)} {name}" for t, name in chapters]
    lines += ["", f"Полная карта: {MAP_URL}", "Сводки по дням:"]
    for d in dates:
        if info["per_day"][d]["n"]:
            dd, mm, _ = dmy(d)
            lines.append(f"▸ {dd} {R.MONTHS[mm]}: https://{SITE}/news/{d}.html")
    lines += [f"Telegram-канал: {B.TG_URL}", "", "Объекты обзора:"]
    for s in sel:
        lines.append(f"— {s.get('city')}: {R.object_name(s, info['refs'])}. {clean_what(s, info['refs'])}")
    if have_bal:
        lines += ["", f"Баланс по оценке карты: остановлено {num_ru(float(nb['capacity_offline_mt_year']))} из "
                      f"{num_ru(float(nb['refining_capacity_total_mt_year']))} млн т/год мощностей ({int(round(nb['capacity_offline_pct']))}%)."]
    if src:
        lines += ["", "Кадры очевидцев: открытые Telegram-каналы, фрагменты до 5 секунд, привязка к месту по данным постов:"]
        lines += [f"— {u}" for u in dict.fromkeys(src)]
        lines = [x if not x.startswith("— http") else x[2:] for x in lines]    # ссылки — без «— »: теги городов берутся только из «— Город:»
    lines += ["", "ОЦЕНКА: агрегация открытых источников (OSINT), не официальная информация. Слухи (rumored) в обзор не включены; "
                  "уровни достоверности: confirmed — подтверждено, reported — сообщается.", "", R.hashtags(sel)]
    return "\n".join(lines) + "\n"


# ───────────────────────────── CLI ─────────────────────────────

def cmd_thumb(end):
    mp4 = VIDEO / "out" / f"weekly-{end}.mp4"
    jpg = mp4.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "6", "-i", str(mp4), "-frames:v", "1",
                    "-vf", "scale=1280:720", "-q:v", "3", str(jpg)], check=True)
    print(jpg)


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("select", "prepare", "compose", "thumb"):
        sys.exit(__doc__)
    cmd, rest = a[0], a[1:]
    end = default_end()
    if "--end-date" in rest:
        i = rest.index("--end-date")
        end = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        sys.exit("--end-date YYYY-MM-DD")
    build = Path(rest[0]) if rest else VIDEO / ".build" / f"weekly-{end}"
    if cmd == "select":
        cmd_select(end)
    elif cmd == "prepare":
        cmd_prepare(end, build)
    elif cmd == "compose":
        compose(end, build)
    else:
        cmd_thumb(end)


if __name__ == "__main__":
    main()
