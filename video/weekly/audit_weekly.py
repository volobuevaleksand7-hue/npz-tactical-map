#!/usr/bin/env python3
"""Аудит недельного обзора: python3 weekly/audit_weekly.py YYYY-MM-DD [weekly|en-weekly]
Код 1 — жёсткий провал (не публиковать): длина вне 180–480 с, не 1920×1080, нет звука/тишина, главы не с 00:00,
кадры очевидцев > трети длины или фрагмент > 5 с, нет дисклеймера ОЦЕНКА, кириллица в EN-описании."""
import json
import re
import subprocess
import sys
from pathlib import Path

VIDEO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import safety as SF  # noqa: E402


def screen_text(html):
    """Видимый текст страницы ролика (без script/style/тегов)."""
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def casualty_hits(date, kind):
    """Озвучка, экранный текст и описание не должны содержать упоминаний погибших/раненых."""
    b = VIDEO / ".build" / f"{kind}-{date}"
    srcs = {"описание": VIDEO / "out" / f"{kind}-{date}.txt"}
    if kind.startswith("en-"):
        srcs["озвучка"] = b / "narration.en.json"
    else:
        srcs["озвучка"] = b / "texts.json"
        srcs["объекты"] = b / "objects.json"
    hits = []
    for name, f in srcs.items():
        if f.exists():
            for m in SF.CASUALTY_ANY.finditer(f.read_text(encoding="utf-8")):
                hits.append(f"{name}: «{m.group(0)}»")
    page = b / "index.html"
    if page.exists():
        for m in SF.CASUALTY_ANY.finditer(screen_text(page.read_text(encoding="utf-8"))):
            hits.append(f"экран: «{m.group(0)}»")
    subs = b / "assets" / "plan.js"
    if subs.exists():
        for m in SF.CASUALTY_ANY.finditer(subs.read_text(encoding="utf-8")):
            hits.append(f"субтитры: «{m.group(0)}»")
    return hits


def probe(mp4):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-show_entries",
                        "format=duration", "-of", "json", str(mp4)], capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    v = next((s for s in j.get("streams", []) if s["codec_type"] == "video"), {})
    a = any(s["codec_type"] == "audio" for s in j.get("streams", []))
    return float(j.get("format", {}).get("duration", 0)), v.get("width"), v.get("height"), a


def loudness(mp4):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    x = re.search(r"max_volume: (-?[\d.]+) dB", r.stderr)
    return (float(m.group(1)) if m else None), (float(x.group(1)) if x else None)


def audit(date, kind):
    hard, warn = [], []
    mp4, txt = VIDEO / "out" / f"{kind}-{date}.mp4", VIDEO / "out" / f"{kind}-{date}.txt"
    if not mp4.exists():
        return [f"нет {mp4}"], []
    dur, w, h, audio = probe(mp4)
    if not 180 <= dur <= 480:
        hard.append(f"длительность {dur:.0f} с вне 180–480")
    if (w, h) != (1920, 1080):
        hard.append(f"разрешение {w}×{h}, нужно 1920×1080")
    if not audio:
        hard.append("нет аудиодорожки")
    else:
        mean, mx = loudness(mp4)
        if mean is None or mean < -40:
            hard.append(f"звук тихий/пустой: mean {mean} dB")
        print(f"audit: громкость mean {mean} dB, max {mx} dB")
    if not txt.exists():
        hard.append("нет описания")
    else:
        t = txt.read_text(encoding="utf-8")
        first = t.splitlines()[0]
        if len(first) > 100:
            hard.append(f"заголовок {len(first)} зн. > 100")
        ch = re.findall(r"^(\d\d):(\d\d) \S", t, re.M)
        if len(ch) < 3 or ch[0] != ("00", "00"):
            hard.append("главы: нужно >=3, первая 00:00")
        if not re.search(r"ОЦЕНКА|ESTIMATE", t):
            hard.append("нет дисклеймера ОЦЕНКА/ESTIMATE")
        if kind.startswith("en-") and re.search(r"[А-Яа-яЁё]", t):
            hard.append("кириллица в EN-описании")
    for h in dict.fromkeys(casualty_hits(date, kind)):
        hard.append(f"упоминание погибших/раненых (запрещено) — {h}")
    plan = VIDEO / ".build" / f"{kind}-{date}" / "assets" / "plan.js"
    if plan.exists():
        p = json.loads(plan.read_text(encoding="utf-8").split("=", 1)[1].strip().rstrip(";"))
        clips = sum(min(c["v1"] - c["v0"], 99) for c in p["clips"])
        longest = max([c["v1"] - c["v0"] for c in p["clips"]] or [0])
        if clips / p["total"] > 0.335:
            hard.append(f"кадры очевидцев {clips:.0f} с = {clips / p['total'] * 100:.0f}% (>1/3)")
        if longest > 5.0:
            hard.append(f"фрагмент очевидцев {longest:.1f} с > 5")
        print(f"audit: кадров очевидцев {clips:.0f} с ({clips / p['total'] * 100:.0f}%), самый длинный {longest:.1f} с")
    return hard, warn


if __name__ == "__main__":
    date = sys.argv[1]
    kind = sys.argv[2] if len(sys.argv) > 2 else "weekly"
    hard, warn = audit(date, kind)
    for x in warn:
        print(f"audit WARN: {x}")
    for x in hard:
        print(f"audit FAIL: {x}")
    print(f"audit {kind} {date}: {'FAIL' if hard else 'OK'} ({len(hard)} жёстких)")
    sys.exit(1 if hard else 0)
