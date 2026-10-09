#!/usr/bin/env python3
"""Английская версия готового рилса для канала Fuel Front (@NPZ-eng).

  python3 reel/en_pass.py KIND DATE      # KIND: reel | urgent | urgent-<метка>

Берёт собранную русскую композицию .build/<KIND>-<DATE>/ (карта, клипы, тайминги уже посчитаны),
копирует в .build/en-<KIND>-<DATE>/, переводит все надписи и реплики одним вызовом Haiku,
озвучивает английским голосом (реплика длиннее своего окна — ускоряется atempo, тайминг кадров
не трогаем), рендерит и сводит звук. Выход: out/en-<KIND>-<DATE>.mp4 + .txt (заголовок/описание)
+ .jpg (обложка). Заливка: NPZ_YT_SECRETS=~/.config/npz-youtube-en python3 upload.py en-<KIND> DATE.
Переменные: REEL_EN_VOICE (en-US-ChristopherNeural), REEL_EN_RATE (+10%).
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REEL = Path(__file__).resolve().parent
VIDEO = REEL.parent
HAIKU = os.environ.get("REEL_LLM_MODEL", "claude-haiku-5-5")
VOICE = os.environ.get("REEL_EN_VOICE", "en-US-ChristopherNeural")
RATE = os.environ.get("REEL_EN_RATE", "+10%")
CYR = re.compile(r"[А-Яа-яЁё]")
SITE = "https://npz-tactical-map.vercel.app/"

PROMPT = """THIS IS AN EXECUTION TASK. Do not ask anything, output only the JSON.

You localize a vertical news short about strikes on Russian fuel infrastructure (refineries, pipelines,
oil depots, power) for an English-speaking audience. Source data: open-source (OSINT) aggregation.
Tone: dry, neutral wire-service English (Reuters/AP style). No slogans, no loaded words, no attribution
or claims beyond the Russian text. Never add facts.

Input JSON:
- "ui": on-screen strings (Russian). Translate each, same order, same count. Keep ALL-CAPS strings in
  ALL CAPS, keep "·" separators, numbers and dates. Keep each string about as short as the original
  (layout is fixed). Glossary: НПЗ -> refinery (in names: "Moscow Refinery (Kapotnya)", "Ryazan Refinery");
  ТОПЛИВНЫЙ ФРОНТ РФ -> FUEL FRONT · RUSSIA; ОЦЕНКА -> ESTIMATE; подтверждено -> confirmed;
  сообщается -> reported; СРОЧНО -> BREAKING; нефтебаза -> oil depot; ЛПДС/НПС -> pumping station;
  обл. -> region; dates 06.10.2026 -> Oct 6, 2026; "6 октября 2026" -> "October 6, 2026".
  Standard English place names (Moscow, Ryazan, Novorossiysk, Tuapse, Bashkortostan, Salavat, Sterlitamak;
  Russian "в" is "v", never "w").
- "voice": spoken lines keyed s0, s1... Translate into natural spoken English, one sentence each,
  no abbreviations, numbers as words if under 20, max ~20 words.
- "context": facts for the intro line.
Also write:
- "intro": one spoken opening line (max 22 words). If context.urgent is true start with "Breaking." Then
  the date and what was hit, then "according to open sources." Briefly orient a foreign viewer
  (e.g. "Russia's oil refining industry" ) without adding facts.
- "title": YouTube title, max 90 chars, plain English, the main object(s) and the date (Oct 6, 2026),
  end with " #shorts".
- "summary": 2-4 short lines for the description, one per strike: "— City: what happened."

Output exactly: {"ui": [...], "voice": {"s0": "..."}, "intro": "...", "title": "...", "summary": ["..."]}

Input:
"""


def log(msg):
    print(f"en_pass: {msg}", flush=True)


def ui_strings(page):
    """Текстовые узлы с кириллицей вне <script>: (уникальные, по порядку)."""
    body = re.sub(r"<script.*?</script>", "", page[page.find("<body"):], flags=re.S)
    seen = []
    for m in re.finditer(r">([^<>]*[А-Яа-яЁё][^<>]*)<", body):
        t = html.unescape(m.group(1))
        if t.strip() and t not in seen:
            seen.append(t)
    return seen


def ask(payload):
    for attempt in range(2):
        r = subprocess.run(["claude", "-p", PROMPT + json.dumps(payload, ensure_ascii=False, indent=1),
                            "--model", HAIKU, "--effort", "high", "--max-budget-usd", "0.30"],
                           capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        m = re.search(r"\{.*\}", r.stdout, re.S)
        try:
            out = json.loads(m.group(0)) if m else None
        except ValueError:
            out = None
        bad = problems(out, payload)
        if not bad:
            return out
        log(f"перевод не прошёл проверку ({bad}), попытка {attempt + 1}: {r.stdout[-300:]!r}")
    raise SystemExit("en_pass: перевод не получен")


def problems(out, payload):
    if not isinstance(out, dict):
        return "не JSON"
    if not (isinstance(out.get("ui"), list) and len(out["ui"]) == len(payload["ui"])):
        return "ui: не та длина"
    if set(out.get("voice") or {}) != set(payload["voice"]):
        return "voice: не те ключи"
    for k in ("intro", "title"):
        if not isinstance(out.get(k), str) or not out[k].strip():
            return f"нет {k}"
    blob = json.dumps(out, ensure_ascii=False)
    if CYR.search(blob):
        return "осталась кириллица"
    return None


def tts(text, out: Path):
    exe = shutil.which("edge-tts") or str(Path.home() / ".local/bin/edge-tts")
    for _ in range(5):
        out.unlink(missing_ok=True)
        subprocess.run([exe, "--voice", VOICE, f"--rate={RATE}", "--text", text, "--write-media", str(out)],
                       capture_output=True, timeout=90)
        if out.exists() and out.stat().st_size > 1000:
            return duration(out)
    raise SystemExit(f"en_pass: голос не сгенерирован для {out.name}")


def duration(p):
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True).stdout.strip()
    return float(d) if d else 0.0


def fit(mp3: Path, slot):
    """Реплика длиннее окна до следующей — ускоряем (не больше ×1.5), кадры не двигаем."""
    d = duration(mp3)
    if d <= slot or slot <= 0:
        return d
    k = min(d / slot, 1.5)
    tmp = mp3.with_suffix(".fit.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-filter:a", f"atempo={k:.3f}", str(tmp)], check=True)
    tmp.replace(mp3)
    log(f"{mp3.name}: {d:.1f} с > окна {slot:.1f} с — ускорено ×{k:.2f}")
    return duration(mp3)


def main():
    if len(sys.argv) != 3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[2]):
        raise SystemExit(__doc__)
    kind, date = sys.argv[1], sys.argv[2]
    src = VIDEO / ".build" / f"{kind}-{date}"
    dst = VIDEO / ".build" / f"en-{kind}-{date}"
    out = VIDEO / "out" / f"en-{kind}-{date}"
    if not (src / "plan.json").exists():
        raise SystemExit(f"en_pass: нет русской сборки {src}")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("silent.mp4", "*.tmp.mp4"))

    page = (dst / "index.html").read_text(encoding="utf-8")
    plan = json.loads((dst / "plan.json").read_text(encoding="utf-8"))
    per = json.loads((dst / "narration.json").read_text(encoding="utf-8"))
    ui = ui_strings(page)
    keys = [Path(v["file"]).stem for v in plan.get("voice", [])]
    payload = {
        "ui": ui,
        "voice": {f"s{i}": t for i, t in enumerate(per) if f"s{i}" in keys},
        "context": {"urgent": kind.startswith("urgent"), "date": date,
                    "headline_ru": next((u for u in ui if u.startswith(("УДАР", "СРОЧНО")) or "УДАР" in u), ""),
                    "description_ru": (dst / "description.txt").read_text(encoding="utf-8")[:1500]},
    }
    tr = ask(payload)
    # Заголовок + описание для upload.py. build.py mix копирует <сборка>/description.txt в out/<имя>.txt
    # (copy2) — в скопированной сборке он русский, и 08.10 английский ролик ушёл с русским заголовком.
    # Поэтому пишем английский именно в description.txt сборки, и сразу в out/ — до рендера.
    # summary от модели бывает не строками — приводим.
    summary = "\n".join(str(s).strip() for s in (tr.get("summary") or []) if str(s).strip())
    desc = (f"{tr['title'].strip()}\n\n"
            f"Strike map (all events, Russian-language site): {SITE}\n"
            f"Fuel Front tracks attacks on fuel infrastructure and the fuel balance, from open sources.\n\n"
            f"{summary}\n\n"
            f"ESTIMATE: aggregated open-source (OSINT) reporting, not official data. "
            f"Footage: public Telegram channels, locations not independently verified.\n\n"
            f"#FuelFront #oil #refinery #Russia #energy #news")
    out.parent.mkdir(exist_ok=True)
    (dst / "description.txt").write_text(desc + "\n", encoding="utf-8")
    out.with_suffix(".txt").write_text(desc + "\n", encoding="utf-8")

    for a, b in zip(ui, tr["ui"]):
        page = page.replace(">" + html.escape(a, quote=False) + "<", ">" + html.escape(b, quote=False) + "<")
        page = page.replace(">" + a + "<", ">" + html.escape(b, quote=False) + "<")
    page = re.sub(r'<html lang="ru"', '<html lang="en"', page)
    left = ui_strings(page)
    if left:
        log(f"не переведено на экране: {left}")
    (dst / "index.html").write_text(page, encoding="utf-8")

    lines = dict(tr["voice"])
    lines["intro"] = tr["intro"]
    lines["outro"] = "Map of all strikes: link in the description."
    lines["broll"] = "Footage from open sources. Locations not independently verified."
    voice = plan.get("voice", [])
    for j, v in enumerate(voice):
        key = Path(v["file"]).stem
        mp3 = dst / v["file"]
        tts(lines[key], mp3)
        end = voice[j + 1]["t"] if j + 1 < len(voice) else plan["total"]
        fit(mp3, end - v["t"] - 0.15)
    (dst / "narration.en.json").write_text(json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")

    env = dict(os.environ, DO_NOT_TRACK="1", HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_NO_UPDATE_CHECK="1",
               HYPERFRAMES_NO_FEEDBACK="1", HYPERFRAMES_NO_AUTO_INSTALL="1")
    subprocess.run([str(VIDEO / "node_modules/.bin/hyperframes"), "render", str(dst), "-o", str(dst / "silent.mp4"),
                    "--quality", os.environ.get("HF_QUALITY", "looks"), "--workers", os.environ.get("HF_WORKERS", "auto"),
                    "--quiet"], check=True, cwd=VIDEO, env=env)
    mp4 = out.with_suffix(".mp4")
    subprocess.run([sys.executable, "build.py", "mix", str(dst), str(dst / "silent.mp4"), str(mp4) + ".tmp.mp4"],
                   check=True, cwd=VIDEO)
    os.replace(str(mp4) + ".tmp.mp4", mp4)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.6", "-i", str(mp4), "-frames:v", "1", "-q:v", "3",
                    str(out.with_suffix(".jpg"))], check=True)

    log(f"готово: {mp4} ({duration(mp4):.1f} с), заголовок: {tr['title']}")


if __name__ == "__main__":
    main()
