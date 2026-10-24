#!/usr/bin/env python3
"""Наблюдатель за YouTube-каналами-хрониками (10.10.2026, просьба владельца): новое видео →
Haiku по заголовку/описанию/субтитрам решает, есть ли крупный удар по объекту на территории РФ
(с 24.10.2026 — любые крупные: ТЭК, промышленность, оборонка, порты, аэродромы, логистика) →
  • удара нет в data/strikes.json — внеочередной проход сборщика ударов (удары не выдумываем:
    сборщик сам проверит по СМИ, дальше strike_pipeline даст молнию и срочный рилс);
  • удар есть — хроника = ещё один источник (video/out/strike-confirm.json: слух с ≥2 источниками идёт в ролик);
    ни в одном вышедшем ролике его не было — срочный рилс через video/reel/urgent_gate.py;
  • лимит Haiku кончился — запасные бесплатные модели OpenRouter (mimo-rotate, YT_FALLBACK_MODELS);
  • по субтитрам ищем таймкод города → подсказка в video/reel/cache/yt-hints.json:
    fetch_clips.fetch_for берёт оттуда кадры (без звука, источник — ссылка YouTube), если в Telegram пусто.
Обнаружение — YouTube API (токен канала), при сбое RSS, затем yt-dlp. LLM только на новое видео.
cron */20. Состояние — /root/.npz-yt-watch/seen.json.
  python3 agents/yt-watch.py [--dry] [--video <id>]"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHANNELS = os.environ.get("NPZ_YT_CHANNELS", "UCoD1pcjTPWhEBTf83SIqmcw,UCS-cgYslpMpH5FkxJ2e0Vpg,UCOHviJPZ2Y2sHdOuqG82t2g").split(",")
# Украина 365, Newsader (10.10), Ян Матвеев (24.10)
STATE = Path(os.environ.get("NPZ_YT_STATE", "/root/.npz-yt-watch/seen.json"))
HINTS = REPO / "video" / "reel" / "cache" / "yt-hints.json"
WORK = Path("/root/.npz-yt-watch/work")
MSK = timezone(timedelta(hours=3))
MAX_AGE_H = 30
YTDLP = os.path.expanduser("~/.local/bin/yt-dlp")
DRY = "--dry" in sys.argv
FALLBACK = os.environ.get("YT_FALLBACK_MODELS", "openrouter/nvidia/nemotron-3.5-lightning:free "
                          "openrouter/nvidia/nemotron-3-super-120b-a12b:free openrouter/poolside/laguna-s-2.1:free "
                          "openrouter/google/gemma-4-31b-it:free")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}

PROMPT = """Ниже свежее видео YouTube-канала новостей войны: заголовок, описание, расшифровка
с секундами в начале строк. Есть ли в нём сообщение о РЕАЛЬНОМ крупном ударе (дроны/ракеты) по объекту
НА ТЕРРИТОРИИ РОССИИ: топливо и энергетика (НПЗ, нефтебаза, терминал, ЛПДС, трубопровод, ГПЗ, электростанция,
подстанция, танкер), промышленность и оборонка (завод, комбинат, химия), транспорт и логистика (порт, аэропорт,
аэродром, ж/д узел, склады), с попаданием, пожаром или пострадавшими?
Не считать: удары по Украине, фронт, оккупированные территории Украины и Крым, всё сбито без попадания,
прогнозы, слухи «могут ударить», политика, экономика без удара, архив прошлых месяцев.
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


def feed_ytdlp(channel, seen):
    """RSS YouTube то и дело отдаёт 404/500 часами (24.10.2026: 01:44–06:44 UTC по всем каналам) —
    тогда список последних роликов берём yt-dlp, метаданные — только для ещё не виденных."""
    r = subprocess.run([YTDLP, "--flat-playlist", "--playlist-end", "8", "--print", "%(id)s",
                        f"https://www.youtube.com/channel/{channel}/videos"], capture_output=True, text=True, timeout=180)
    out = []
    for vid in r.stdout.split():
        if vid in seen:
            continue
        m = subprocess.run([YTDLP, "-j", "--skip-download", f"https://www.youtube.com/watch?v={vid}"],
                           capture_output=True, text=True, timeout=180)
        try:
            j = json.loads(m.stdout)
        except ValueError:
            continue
        ts = j.get("timestamp") or j.get("release_timestamp")
        if not ts:
            continue
        out.append({"id": vid, "title": j.get("title") or "", "channel": channel,
                    "published": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
                    "desc": (j.get("description") or "")[:1500]})
    if not out and r.returncode:
        raise RuntimeError(r.stderr[-200:])
    return out


def yt_access_token():
    """Refresh-токен загрузчика НПЗ. В лог не попадает."""
    cached = getattr(yt_access_token, "value", None)
    if cached:
        return cached
    sys.path.insert(0, str(REPO / "video"))
    import upload
    try:
        yt_access_token.value = upload.access_token()
    except SystemExit as e:
        raise RuntimeError(str(e)[:200]) from None
    return yt_access_token.value


def api_json(path, params, token):
    url = "https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "User-Agent": "npz-yt-watch"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from None


def feed_api(channel):
    """Последние ролики: playlistItems.list (uploads) и videos.list snippet."""
    if not channel.startswith("UC") or len(channel) < 4:
        raise RuntimeError("плохой id канала")
    token = yt_access_token()
    data = api_json("playlistItems", {
        "part": "contentDetails", "maxResults": "15", "playlistId": "UU" + channel[2:],
    }, token)
    ids = [it.get("contentDetails", {}).get("videoId") for it in data.get("items") or []]
    ids = [v for v in ids if v]
    if not ids:
        raise RuntimeError("пустой список")
    vids = api_json("videos", {"part": "snippet", "id": ",".join(ids)}, token)
    by_id = {it["id"]: it for it in vids.get("items") or []}
    out = []
    for vid in ids:
        sn = (by_id.get(vid) or {}).get("snippet") or {}
        published = (sn.get("publishedAt") or "").replace("Z", "+00:00")
        if not published:
            continue
        out.append({"id": vid, "title": sn.get("title") or "", "published": published,
                    "channel": channel, "desc": (sn.get("description") or "")[:1500]})
    if not out:
        raise RuntimeError("пустой список")
    return out


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
    # 12.10.2026: недельный лимит Haiku — yt-watch молчал весь вечер. Второй заход — бесплатные модели
    # OpenRouter через mimo-rotate (в промпте только публичные заголовок/описание/субтитры, секретов нет).
    calls = [("haiku", ["claude-run", "-p", p, "--model", "claude-haiku-5-5", "--effort", "high"], {}),
             ("openrouter", ["mimo-rotate", p], {"MIMO_MODELS": FALLBACK, "MIMO_TIMEOUT": "240",
                                                 "LLM_CALLER": "npz-yt-watch"})]
    for name, cmd, env in calls:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=dict(os.environ, **env))
            m = re.search(r"\{\s*\"strikes\".*\}", r.stdout, re.S)
            if m:
                return json.loads(m.group(0)).get("strikes") or []
            log(f"{name} без JSON: {r.stdout[-150:]!r} {r.stderr[-150:]!r}")
        except Exception as e:  # noqa: BLE001
            log(f"{name}: {e}")
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
        log(f"{v['id']}: крупных ударов по РФ нет — «{v['title'][:80]}»")
        return True
    log(f"{v['id']}: удары {[(s.get('city'), s.get('object'), s.get('match'), s.get('start')) for s in found]}"
        f" — «{v['title'][:80]}»")
    missing, uncovered = [], []
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
        if not DRY and gate().confirm(r, f"yt:{v['channel']}", url):
            log(f"{v['id']}: второй источник для {r.get('city')} ({r.get('confidence')})")
        if strike_id(r) not in shown_ids(str(r["date"])[:10]):
            uncovered.append(r)
    if missing:
        alert(f"📺 Хроника: {', '.join(missing)} — в данных нет, запускаю сборщик ударов.\n{url}")
        launch(f"cd {REPO} && NPZ_MODEL=claude-haiku-5-5 NPZ_LOCK_WAIT=900 ./agents/run-agent.sh "
               f"{REPO}/agents/update-prompt-strikes.md strikes-yt >> {REPO}/agents/logs/cron.log 2>&1")
    if uncovered:
        jobs, ask, over = gate().dispatch(uncovered, by=f"YouTube {v['id']}", dry=DRY)
        for j in jobs:
            log(f"срочный {j['kind']} {j['date']}: {len(j['ids'])} уд., слот {j['slot'][11:16]} UTC")
            if not DRY:
                alert(f"📺 Хроника: удар есть в данных, но без ролика — срочный {j['kind']} {j['date']}"
                      f"{' (слух, ≥2 источника)' if j['rumored'] else ''}.\n{url}")
        if over:
            log(f"лимит срочных за сутки — {len(over)} уд. уйдут в сводку")
    return True


def gate():
    sys.path.insert(0, str(REPO / "video" / "reel"))
    import urgent_gate
    return urgent_gate


def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    seen = json.loads(STATE.read_text()) if STATE.exists() else {}
    hints = json.loads(HINTS.read_text()) if HINTS.exists() else {}
    only = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else None
    now = datetime.now(timezone.utc)
    for ch in CHANNELS:
        items = None
        try:
            items = feed_api(ch)
            log(f"{ch}: список через API ({len(items)})")
        except Exception as e:  # noqa: BLE001
            log(f"{ch}: API: {e}")
            try:
                items = feed(ch)
            except Exception as e2:  # noqa: BLE001
                try:
                    items = feed_ytdlp(ch, seen)
                    log(f"{ch}: RSS: {e2} — взял список через yt-dlp ({len(items)} новых)")
                except Exception as e3:  # noqa: BLE001
                    log(f"{ch}: API: {e}; RSS: {e2}; yt-dlp: {e3}")
                    continue
        if not items:
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
