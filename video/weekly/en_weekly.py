#!/usr/bin/env python3
"""Английская версия недельного обзора для канала Fuel Front (@NPZ-eng).

  python3 weekly/en_weekly.py YYYY-MM-DD        # дата = последний день недели

Берёт готовую русскую композицию .build/weekly-<D>/ (карта, кадры, тайминги), переводит надписи, реплики,
названия глав и список объектов одним вызовом Haiku (как reel/en_pass.py), озвучивает en-US-ChristopherNeural
(реплика длиннее окна ускоряется atempo <= 1.5), пересчитывает субтитры, рендерит и сводит звук.
Выход: out/en-weekly-<D>.mp4 + .txt (заголовок/описание) + .jpg. Заливка: NPZ_YT_SECRETS=~/.config/npz-youtube-en
python3 upload.py en-weekly <D>.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO = HERE.parent
sys.path.insert(0, str(VIDEO / "reel"))
sys.path.insert(0, str(HERE))
import en_pass as E                  # noqa: E402
import build_weekly as W             # noqa: E402
import safety as SF                  # noqa: E402

SITE = "https://npz-tactical-map.vercel.app/?utm_source=youtube_en&utm_medium=weekly"
MON_EN = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

PROMPT = """THIS IS AN EXECUTION TASK. Do not ask anything, output only the JSON.

You localize a 16:9 weekly news review about strikes on Russian fuel infrastructure (refineries, pipelines,
oil depots, power) for an English-speaking audience. Source data: open-source (OSINT) aggregation, assessments.
Tone: dry, neutral wire-service English (Reuters/AP style). No slogans, no loaded words, no claims beyond
the Russian text. Never add facts. Keep every number as is.

Input JSON:
- "ui": on-screen strings (Russian). Translate each, same order, same count. Keep ALL-CAPS strings in ALL CAPS,
  keep "·" separators and numbers. Keep each string about as short as the original (layout is fixed).
  Glossary: НПЗ -> refinery (in names: "Moscow Refinery (Kapotnya)", "Ryazan Refinery"); ТОПЛИВНЫЙ ФРОНТ РФ ->
  FUEL FRONT · RUSSIA; ОЦЕНКА -> ESTIMATE; ПОДТВЕРЖДЕНО -> CONFIRMED; СООБЩАЕТСЯ -> REPORTED;
  МОЩНОСТЬ -> CAPACITY; млн т/год -> mt/yr; остановлен -> offline; частично -> partial; работает -> operating;
  ПН ВТ СР ЧТ ПТ СБ ВС -> MON TUE WED THU FRI SAT SUN; month abbreviations ЯНВ.. -> JAN..; "4 ОКТ" -> "OCT 4";
  "4–10 ОКТЯБРЯ" -> "OCT 4–10"; dates dd.mm stay dd.mm. Standard English place names (Moscow, Ryazan, Salavat,
  Sterlitamak, Omsk, Ukhta, Saratov, Samara; Russian "в" is "v").
- Never mention people killed, wounded or injured, casualties or victims, even if the Russian text hints at it:
  state only the strike, the facility and damage to infrastructure. Keep neutral source notes such as
  "Crimea, according to open sources" as given.
- "voice": spoken lines keyed by id. Translate into natural spoken English, same meaning and facts, no
  abbreviations, max ~1.3x the length of the Russian line. Dates as "October 4th". "миллиона тонн" -> "million tonnes".
- "chapters": short YouTube chapter names (translate, same order).
- "objects": [{"city","object","what","date"}] -> "summary": same order, one line each: "— City: Object. What happened."
  (what happened in one short neutral sentence, only facts from "what").
Output exactly: {"ui": [...], "voice": {"id": "..."}, "chapters": [...], "summary": [...]}

Input:
"""


def log(m):
    print(f"en_weekly: {m}", flush=True)


def ask(payload):
    for attempt in range(3):
        r = subprocess.run(["claude-run", "-p", PROMPT + json.dumps(payload, ensure_ascii=False, indent=1),
                            "--model", E.HAIKU, "--effort", "high", "--max-budget-usd", "0.60"],
                           capture_output=True, text=True, timeout=420, stdin=subprocess.DEVNULL)
        m = re.search(r"\{.*\}", r.stdout, re.S)
        try:
            out = json.loads(m.group(0)) if m else None
        except ValueError:
            out = None
        bad = None
        if not isinstance(out, dict):
            bad = "не JSON"
        elif not (isinstance(out.get("ui"), list) and len(out["ui"]) == len(payload["ui"])):
            bad = "ui: не та длина"
        elif set(out.get("voice") or {}) != set(payload["voice"]):
            bad = "voice: не те ключи"
        elif not (isinstance(out.get("chapters"), list) and len(out["chapters"]) == len(payload["chapters"])):
            bad = "chapters: не та длина"
        elif not (isinstance(out.get("summary"), list) and len(out["summary"]) == len(payload["objects"])):
            bad = "summary: не та длина"
        elif E.CYR.search(json.dumps(out, ensure_ascii=False)):
            bad = "осталась кириллица"
        elif SF.has_casualty(json.dumps(out, ensure_ascii=False)):
            bad = "упоминание погибших/раненых (запрещено)"
        if not bad:
            return out
        log(f"перевод не прошёл проверку ({bad}), попытка {attempt + 1}: {r.stdout[-200:]!r}")
    raise SystemExit("en_weekly: перевод не получен")


def en_range(dates):
    (d1, m1, y), (d2, m2, _) = W.dmy(dates[0]), W.dmy(dates[-1])
    if m1 == m2:
        return f"{MON_EN[m2]} {d1}–{d2}, {y}"
    return f"{MON_EN[m1]} {d1} – {MON_EN[m2]} {d2}, {y}"


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        raise SystemExit(__doc__)
    date = sys.argv[1]
    src, dst = VIDEO / ".build" / f"weekly-{date}", VIDEO / ".build" / f"en-weekly-{date}"
    out = VIDEO / "out" / f"en-weekly-{date}"
    if not (src / "plan.json").exists():
        raise SystemExit(f"en_weekly: нет русской сборки {src}")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("silent.mp4", "*.tmp.mp4"))
    page = (dst / "index.html").read_text(encoding="utf-8")
    page = re.sub(r'<div class="cta-tg">.*?</div>', "", page, flags=re.S)     # Telegram-канал русскоязычный
    plan = json.loads((dst / "plan.json").read_text(encoding="utf-8"))
    texts = json.loads((dst / "texts.json").read_text(encoding="utf-8"))
    ob = json.loads((dst / "objects.json").read_text(encoding="utf-8"))
    chapters = json.loads((dst / "chapters.json").read_text(encoding="utf-8"))
    ui = E.ui_strings(page)
    keys = [Path(v["file"]).stem for v in plan["voice"]]
    payload = {"ui": ui, "voice": {k: texts[k] for k in keys}, "chapters": [c[1] for c in chapters], "objects": ob["objects"]}
    tr = ask(payload)

    rng = en_range(ob["dates"])
    title = f"Strikes on Russian Refineries This Week, {rng}: Recap, Map, Balance"[:100]
    n, m = ob["N"], ob["M"]
    lines = [title, "",
             f"Weekly recap, {rng}: {n} strike{'s' if n != 1 else ''} across Russia" + (f", {m} of them on refineries and energy." if m else ".")
             + " Open-source (OSINT) assessment of fuel infrastructure hits, capacities and refinery status.", "", "Chapters:"]
    lines += [f"{W.mmss(c[0])} {name.strip()}" for c, name in zip(chapters, tr["chapters"])]
    lines += ["", f"Strike map (all events, Russian-language site): {SITE}", "", "Objects covered:"]
    lines += [re.sub(r"^[-–—]*\s*", "— ", str(s).strip()) for s in tr["summary"]]
    if ob.get("bal"):
        b = ob["bal"]
        lines += ["", f"Refining balance (map estimate): {b['offline']} of {b['total']} mt/yr of capacity offline ({int(round(b['pct']))}%)."]
    lines += ["", "ESTIMATE: aggregated open-source (OSINT) reporting, not official data. Rumored reports are excluded; "
                  "items are marked confirmed or reported. Footage: short fragments from public Telegram channels, "
                  "locations not independently verified.", "",
              "#FuelFront #oil #refinery #Russia #drones " + E.en_city_tags("\n".join(lines)) + "#news"]
    desc = "\n".join(lines) + "\n"
    if E.CYR.search(desc):
        raise SystemExit("en_weekly: кириллица в описании")
    (dst / "description.txt").write_text(desc, encoding="utf-8")
    out.parent.mkdir(exist_ok=True)
    out.with_suffix(".txt").write_text(desc, encoding="utf-8")

    for a, b in zip(ui, tr["ui"]):
        page = page.replace(">" + html.escape(a, quote=False) + "<", ">" + html.escape(b, quote=False) + "<")
        page = page.replace(">" + a + "<", ">" + html.escape(b, quote=False) + "<")
        page = page.replace(">" + html.escape(a, quote=True) + "<", ">" + html.escape(b, quote=False) + "<")
        page = page.replace(">" + html.escape(a, quote=True).replace("&#x27;", "&#39;") + "<", ">" + html.escape(b, quote=False) + "<")
    page = re.sub(r'<html lang="ru"', '<html lang="en"', page)
    left = E.ui_strings(page)
    if left:
        log(f"не переведено на экране: {left}")
    (dst / "index.html").write_text(page, encoding="utf-8")

    voice, subs = plan["voice"], []
    E.tts_all([(tr["voice"][Path(v["file"]).stem], dst / v["file"]) for v in voice])   # каскад озвучки, один провайдер
    for j, v in enumerate(voice):
        k = Path(v["file"]).stem
        mp3 = dst / v["file"]
        nxt = voice[j + 1]["t"] if j + 1 < len(voice) else plan["total"]
        d = E.fit(mp3, nxt - v["t"] - 0.15)
        subs += W.sub_chunks(tr["voice"][k], v["t"], d)
    pj = dst / "assets" / "plan.js"
    pl = json.loads(pj.read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))
    pl["subs"] = subs
    pj.write_text("window.PLAN = " + json.dumps(pl, ensure_ascii=False) + ";\n", encoding="utf-8")
    (dst / "narration.en.json").write_text(json.dumps(tr["voice"], ensure_ascii=False, indent=1), encoding="utf-8")

    env = dict(os.environ, DO_NOT_TRACK="1", HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_UPDATE_CHECK="1",
               HYPERFRAMES_NO_FEEDBACK="1", HYPERFRAMES_NO_AUTO_INSTALL="1")
    subprocess.run([str(VIDEO / "node_modules/.bin/hyperframes"), "render", str(dst), "-o", str(dst / "silent.mp4"),
                    "--quality", os.environ.get("HF_QUALITY", "looks"), "--workers", os.environ.get("HF_WORKERS", "auto"),
                    "--fps", os.environ.get("HF_FPS", "24"), "--quiet"], check=True, cwd=VIDEO, env=env)
    mp4 = out.with_suffix(".mp4")
    subprocess.run([sys.executable, "build.py", "mix", str(dst), str(dst / "silent.mp4"), str(mp4) + ".tmp.mp4"],
                   check=True, cwd=VIDEO)
    os.replace(str(mp4) + ".tmp.mp4", mp4)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "6", "-i", str(mp4), "-vf", "scale=1280:720", "-frames:v", "1",
                    "-q:v", "3", str(out.with_suffix(".jpg"))], check=True)
    log(f"готово: {mp4} ({E.duration(mp4):.1f} с), заголовок: {title}")


if __name__ == "__main__":
    main()
