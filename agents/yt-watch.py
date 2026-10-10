#!/usr/bin/env python3
"""Наблюдатель за YouTube-каналами-хрониками (10.10.2026, просьба владельца): новое видео →
Haiku по заголовку/описанию решает, есть ли реальный удар по топливу/энергетике РФ →
  • удара нет в data/strikes.json — внеочередной проход сборщика ударов (удары не выдумываем:
    сборщик сам проверит по СМИ, дальше strike_pipeline даст молнию и срочный рилс);
  • удар есть, но ни в одном вышедшем ролике его не было — срочный рилс сразу;
  • по субтитрам ищем таймкод города → подсказка в video/reel/cache/yt-hints.json:
    fetch_clips.fetch_for берёт оттуда кадры (без звука, источник — ссылка YouTube), если в Telegram пусто.
Обнаружение — RSS, без LLM; LLM только на новое видео. cron */20. Состояние — /root/.npz-yt-watch/seen.json.
  python3 agents/yt-watch.py [--dry] [--video <id>]"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHANNELS = os.environ.get("NPZ_YT_CHANNELS", "UCoD1pcjTPWhEBTf83SIqmcw,UCS-cgYslpMpH5FkxJ2e0Vpg").split(",")   # Украина 365, Newsader (10.10)
STATE = Path(os.environ.get("NPZ_YT_STATE", "/root/.npz-yt-watch/seen.json"))
HINTS = REPO / "video" / "reel" / "cache" / "yt-hints.json"
WORK = Path("/root/.npz-yt-watch/work")
MSK = timezone(timedelta(hours=3))
MAX_AGE_H = 30
YTDLP = os.path.expanduser("~/.local/bin/yt-dlp")
DRY = "--dry" in sys.argv
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}

PROMPT = """Ниже свежее видео YouTube-канала новостей войны: заголовок, описание, расшифровка
с секундами в начале строк. Есть ли в нём сообщение о РЕАЛЬНОМ ударе (дроны/ракеты) по объекту
топливно-энергетической инфраструктуры НА ТЕРРИТОРИИ РОССИИ: НПЗ, нефтебаза, нефтяной/наливной терминал,
ЛПДС, нефтепровод, резервуарный парк, ГПЗ, электростанция, подстанция, порт с танкерами, танкер?
Не считать: удары по Украине, фронт, оккупированные территории Украины, прогнозы, слухи «могут ударить»,
политика, экономика без удара, архив прошлых месяцев.
Для каждого удара: если это тот же удар, что в списке «Уже в данных» (тот же объект/населённый пункт,
даже если в видео назван областной центр или имя терминала) — укажи его номер в match, иначе null.
start — секунда расшифровки, с которой в видео рассказывают/показывают этот удар (null — не понять).
Ответь только JSON: {"strikes": [{"city": "населённый пункт РФ, именительный падеж", "region": "область",
"object": "объект коротко", "match": номер|null, "start": секунда|null}]}. Нет таких — {"strikes": []}.

Дата публикации: {date}
Заголовок: {title}
Описание: {desc}

Уже в данных (удары за сегодня и вчера):
{known}

Расшифровка:
{subs}"""


def log(*a):
    print(f"[{datetime.now(timezone.utc):%FT%TZ}] yt-watch:", *a, flush=True)


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def feed(channel):
    root = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel}"))
    out = []
    for e in root.findall("a:entry", NS):
        g = e.find("m:group", NS)
        out.append({"id": e.findtext("yt:videoId", "", NS), "title": e.findtext("a:title", "", NS),
                    "published": e.findtext("a:published", "", NS), "channel": channel,
                    "desc": (g.findtext("m:description", "", NS) if g is not None else "")[:1500]})
    return out


def ask_haiku(v, known, cues):
    lines, last = [], None
    for t, txt in cues:
        if txt != last:
            lines.append(f"{t} {txt}")
            last = txt
    p = (PROMPT.replace("{date}", v["published"][:16]).replace("{title}", v["title"])
         .replace("{desc}", v["desc"] or "—").replace("{subs}", "\n".join(lines)[:6000] or "—")
         .replace("{known}", "\n".join(f"{i + 1}. {r.get('date')} {r.get('city')}, {r.get('region') or ''} — "
                                       f"{str(r.get('target') or '')[:90]}" for i, r in enumerate(known)) or "—"))
    for _ in range(2):
        try:
            r = subprocess.run(["claude-run", "-p", p, "--model", "claude-haiku-5-5", "--effort", "high"],
                               capture_output=True, text=True, timeout=180)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if m:
                return json.loads(m.group(0)).get("strikes") or []
            log(f"haiku без JSON: {r.stdout[-150:]!r} {r.stderr[-150:]!r}")
        except Exception as e:  # noqa: BLE001
            log(f"haiku: {e}")
    return None


def stem(city):
    c = re.sub(r"\s+(район|область|округ)$", "", str(city or "").strip(), flags=re.I)
    c = c.split()[0] if c else ""
    return c[:-1].lower() if len(c) > 5 else c.lower()   # как fetch_clips.city_stem: ловит падежи


def subs(vid):
    """Авто-субтитры ru → [(сек, текст)]."""
    d = WORK / vid
    d.mkdir(parents=True, exist_ok=True)
    if not list(d.glob("*.vtt")):
        subprocess.run([YTDLP, "-q", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "ru.*,ru",
                        "--sub-format", "vtt", "-o", str(d / "s.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, text=True, timeout=120)
    files = sorted(d.glob("*.vtt"))
    if not files:
        return []
    cues, t = [], None
    for line in files[0].read_text(errors="ignore").splitlines():
        m = re.match(r"(\d+):(\d\d):(\d\d)\.\d+ -->", line)
        if m:
            t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        elif t is not None and line.strip() and "-->" not in line:
            cues.append((t, re.sub(r"<[^>]+>", "", line).lower()))
    return cues


def find_start(cues, st):
    for t, txt in cues:
        if st and st in txt:
            return max(0, t - 1)
    return None


def recent_strikes():
    data = json.loads((REPO / "data" / "strikes.json").read_text())
    rows = data if isinstance(data, list) else data.get("strikes", [])
    today = datetime.now(MSK).date()
    days = {str(today), str(today - timedelta(days=1))}
    return [s for s in rows if str(s.get("date", ""))[:10] in days]


def strike_id(s):
    sys.path.insert(0, str(REPO / "hermes" / "bot"))
    from strike_pipeline import _strike_id   # тот же id, что у молнии/рилсов
    return _strike_id(s)


def shown_ids(date):
    """id ударов в вышедших за дату роликах (срочные + сводки) и в собранных за последние 3 ч (ждут выхода)."""
    v = REPO / "video"
    ids = set(json.loads((v / "out" / "reel-shown.json").read_text())) if (v / "out" / "reel-shown.json").exists() else set()
    for f in (v / ".build").glob(f"*-{date}/ids.json"):
        kind = f.parent.name[: -len(date) - 1]
        fresh = datetime.now().timestamp() - f.stat().st_mtime < 3 * 3600   # собирается/ждёт выхода
        if (v / "out" / f"{kind}-{date}.uploaded").exists() or fresh:
            ids |= set(json.loads(f.read_text()))
    return ids


def video_busy():
    r = subprocess.run(["pgrep", "-f", "reel/daily.sh"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def launch(cmd, env=None):
    log("запуск:", cmd)
    if DRY:
        return
    subprocess.Popen(["bash", "-c", cmd], env=dict(os.environ, **(env or {})), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def alert(text):
    try:
        t = Path("/root/.npz-bot/token").read_text().strip()
        c = Path("/root/.npz-bot/chat_id").read_text().strip()
    except OSError:
        return
    if DRY:
        return log("alert:", text)
    body = urllib.parse.urlencode({"chat_id": c, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{t}/sendMessage", body, timeout=20)
    except Exception as e:  # noqa: BLE001
        log(f"alert: {e}")


def handle(v, hints):
    url = f"https://www.youtube.com/watch?v={v['id']}"
    rows = recent_strikes()
    cues = subs(v["id"])
    found = ask_haiku(v, rows, cues)
    if found is None:
        return False          # модель не ответила — повторим следующим проходом
    if not found:
        log(f"{v['id']}: ударов по топливу РФ нет — «{v['title'][:80]}»")
        return True
    log(f"{v['id']}: удары {[(s.get('city'), s.get('object'), s.get('match'), s.get('start')) for s in found]}"
        f" — «{v['title'][:80]}»")
    missing, uncovered = [], {}
    for s in found:
        m = s.get("match")
        r = rows[m - 1] if isinstance(m, int) and 1 <= m <= len(rows) else None
        city = (r or s).get("city")
        st = stem(city)
        if not st:
            continue
        start = s.get("start") if isinstance(s.get("start"), (int, float)) else find_start(cues, st)
        hints[f"{v['id']}:{st}"] = {"url": url, "video": v["id"], "title": v["title"], "city": city,
                                    "stem": st, "object": s.get("object"), "start": start,
                                    "published": v["published"], "added": datetime.now(timezone.utc).isoformat()}
        if not r:
            missing.append(f"{s.get('city')} ({s.get('object')})")
            continue
        d = str(r["date"])[:10]
        sid = strike_id(r)
        if sid not in shown_ids(d):
            uncovered.setdefault(d, []).append(sid)
    if missing:
        alert(f"📺 Ukraine365: {', '.join(missing)} — в данных нет, запускаю сборщик ударов.\n{url}")
        launch(f"cd {REPO} && NPZ_MODEL=claude-haiku-5-5 NPZ_LOCK_WAIT=900 ./agents/run-agent.sh "
               f"{REPO}/agents/update-prompt-strikes.md strikes-yt >> {REPO}/agents/logs/cron.log 2>&1")
    for d, ids in uncovered.items():
        v_dir = REPO / "video" / "out"
        kind = "urgent" if not (v_dir / f"urgent-{d}.uploaded").exists() else (
            "urgent-yt" if not (v_dir / f"urgent-yt-{d}.uploaded").exists() else None)
        if not kind:
            log(f"{d}: срочные за дату исчерпаны — удары уйдут в сводку")
            continue
        alert(f"📺 Ukraine365: удар есть в данных, но без ролика — срочный {kind} {d}.\n{url}")
        launch(f"cd {REPO}/video && flock -w 3600 /var/lock/npz-video.lock nice -n 10 ./reel/daily.sh {d} "
               f">> {REPO}/agents/logs/video.log 2>&1", {"REEL_KIND": kind, "REEL_ONLY": ",".join(sorted(set(ids)))})
    return True


def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    seen = json.loads(STATE.read_text()) if STATE.exists() else {}
    hints = json.loads(HINTS.read_text()) if HINTS.exists() else {}
    only = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    now = datetime.now(timezone.utc)
    for ch in CHANNELS:
        try:
            items = feed(ch)
        except Exception as e:  # noqa: BLE001
            log(f"{ch}: RSS: {e}")
            continue
        for v in items:
            if only and v["id"] != only:
                continue
            if v["id"] in seen and not only:
                continue
            age = now - datetime.fromisoformat(v["published"])
            if age > timedelta(hours=MAX_AGE_H) and not only:
                seen[v["id"]] = "old"
                continue
            if handle(v, hints):
                seen[v["id"]] = now.isoformat()
    cutoff = (now - timedelta(days=3)).isoformat()
    hints = {k: h for k, h in hints.items() if h.get("added", "") >= cutoff}
    if not DRY:
        HINTS.parent.mkdir(parents=True, exist_ok=True)
        tmp = HINTS.with_suffix(".tmp")
        tmp.write_text(json.dumps(hints, ensure_ascii=False, indent=1))
        os.replace(tmp, HINTS)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(seen, indent=0))
        os.replace(tmp, STATE)


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    main()
