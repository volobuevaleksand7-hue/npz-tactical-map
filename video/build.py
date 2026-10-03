#!/usr/bin/env python3
"""Сборка ежедневного ролика-сводки: данные проекта -> HyperFrames-композиция -> звук.

  python3 video/build.py compose <YYYY-MM-DD> <build_dir>   # index.html + assets + plan.json
  python3 video/build.py mix <build_dir> <silent.mp4> <out.mp4>  # эффекты (+музыка) поверх видео
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


# ───────────────────────────────── compose ─────────────────────────────────

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

    # тайминги
    s2 = 4.2
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

    plan = {"s2": s2, "s3": s3, "s4": s4, "total": total, "count": n,
            "cards": card_t, "more": more_t}
    host = G.SITE.split("://", 1)[-1]
    subs = {
        "TOTAL": total, "S1_DUR": s2 + X, "S2_START": s2,
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
        "PLAN_JSON": json.dumps(plan),
    }
    page = (TEMPLATE / "index.html").read_text(encoding="utf-8")
    page = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: str(subs[m.group(1)]), page)
    (build / "index.html").write_text(page, encoding="utf-8")
    (build / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}}), encoding="utf-8")

    # звуковые события для mix: вжух на каждой смене сцены, удар на цифре, щелчки на карточках
    events = [("whoosh", s2 - 0.25)]
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
    (build / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: plan[k] for k in ("date", "total", "strikes", "refinery_strikes",
                                           "cards_total", "cards_shown", "cover")}, ensure_ascii=False))


# ───────────────────────────────── mix ─────────────────────────────────

SFX_GAIN = {"whoosh": 1.6, "impact": 1.0, "click": 0.8}


def pick_music(date: str):
    files = sorted(p for p in MUSIC.iterdir() if p.is_file() and p.suffix.lower() in MUSIC_EXT) \
        if MUSIC.is_dir() else []
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
