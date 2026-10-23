#!/usr/bin/env python3
"""Диспетчер срочных роликов (24.10.2026, решение владельца): отдельный срочный на каждый крупный удар.
  • удары одной даты в пределах 2 ч — один ролик (ночной налёт по нескольким объектам — одна история);
  • не больше URGENT_MAX (5) срочных за 24 ч, между выходами ≥ URGENT_GAP_MIN (60) мин: запуск ждёт свой слот
    sleep-ом ДО лока видео (лок не держим — рилс дня не стоит в очереди за паузой); сверх лимита — в сводку дня;
  • rumored — сам, если у удара ≥2 независимых источника: ссылки удара (source_url, *_alt, merged_sources),
    подтверждения YouTube-хроник (agents/yt-watch.py → out/strike-confirm.json), посты каналов-хроник Telegram
    с городом и атакой в окне даты. Один источник — владельцу кнопка «🎬 Срочный ролик» (radar_publish.handle_callback
    → approve). В ролике слухи помечены: «По неподтверждённым данным», «НЕ ПОДТВЕРЖДЕНО · OSINT» (build_reel.py);
  • удар уже был в срочном (out/urgent-log.json) — повтор не запускаем.
Kind ролика — urgent-<id6> (daily.sh, upload.py, tg_post.py, gen-news.py понимают urgent-*).
  python3 video/reel/urgent_gate.py plan <id,...>     — вхолостую: что и когда запустится, ничего не пишет
  python3 video/reel/urgent_gate.py run <id,...>      — запустить (как молния)
  python3 video/reel/urgent_gate.py approve <id>      — то же, что кнопка владельца"""
import fcntl
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

REEL = Path(__file__).resolve().parent
VIDEO = REEL.parent
REPO = VIDEO.parent
OUT = VIDEO / "out"
LOG_F = OUT / "urgent-log.json"        # [{kind, date, ids, rumored, slot, by}] + {"asked": sid} — кнопки владельцу
CONF_F = OUT / "strike-confirm.json"   # {sid: {"yt:<канал>": url}} — подтверждения от yt-watch
MAX_DAY = int(os.environ.get("URGENT_MAX", "5"))
GAP = timedelta(minutes=int(os.environ.get("URGENT_GAP_MIN", "60")))
MERGE_MIN = 120
MSK = timezone(timedelta(hours=3))
PART_OF_DAY = {"ночь": 180, "утро": 480, "день": 780, "вечер": 1140}


def log(*a):
    print("urgent_gate:", *a, flush=True)


def strike_id(raw):
    """= strike_pipeline._strike_id / build_reel.strike_id."""
    import hashlib
    parts = [str(raw.get("date", "")), str(raw.get("time", "")), str(raw.get("city", "")),
             str(raw.get("target", ""))[:80]]
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def strikes():
    d = json.loads((REPO / "data" / "strikes.json").read_text())
    return d if isinstance(d, list) else d.get("strikes", [])


def jread(f, dflt):
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return dflt


@contextmanager
def locked():
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / ".urgent-gate.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def jwrite(f, obj):
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, f)


# ── источники ────────────────────────────────────────────────────────────────
def src_key(url):
    u = str(url or "").strip()
    m = re.match(r"https?://t\.me/(?:s/)?([A-Za-z0-9_]+)", u)
    if m:
        return "tg:" + m.group(1).lower()
    host = urllib.parse.urlparse(u).netloc.lower().removeprefix("www.")
    return ("web:" + host) if host else None


def own_sources(s):
    urls = [s.get("source_url"), s.get("source_url_2")]
    for k in ("source_url_alt", "merged_sources"):
        v = s.get(k)
        urls += v if isinstance(v, list) else [v]
    return {k for k in map(src_key, urls) if k}


def tg_sources(s):
    """Каналы-хроники Telegram с постом про атаку на город в окне даты (без модели: только как второй голос)."""
    try:
        sys.path.insert(0, str(REEL))
        import fetch_clips as fc
    except Exception as e:  # noqa: BLE001
        log(f"fetch_clips недоступен: {e}")
        return set()
    stem, day = fc.city_stem(s.get("city")), str(s.get("date", ""))[:10]
    out = set()
    if not stem:
        return out
    for chan in fc.CHANNELS:
        try:
            posts = fc.tg_search(chan, stem)
        except Exception:  # noqa: BLE001
            continue
        if any(stem in p["text"].lower() and fc.ATTACK_RX.search(p["text"]) and fc.date_ok(p["date"], day)
               for p in posts):
            out.add("tg:" + chan.lower())
    return out


def sources(s, deep=True):
    sid = strike_id(s)
    keys = own_sources(s) | set(jread(CONF_F, {}).get(sid, {}))
    if deep and len(keys) < 2:
        keys |= tg_sources(s)
    return keys


def confirm(s, key, url):
    """yt-watch: YouTube-хроника рассказала об этом ударе — второй источник."""
    sid = strike_id(s)
    with locked():
        c = jread(CONF_F, {})
        if key in c.get(sid, {}):
            return False
        c.setdefault(sid, {})[key] = url
        jwrite(CONF_F, c)
    return True


# ── план ─────────────────────────────────────────────────────────────────────
def minute(s):
    t = str(s.get("time") or "").strip().lower()
    m = re.match(r"(\d{1,2})[:.](\d\d)", t)
    if m:
        return int(m[1]) * 60 + int(m[2])
    return next((v for k, v in PART_OF_DAY.items() if t.startswith(k)), None)


def plan(rows, approved=(), now=None, deep=True):
    """-> (запуски [{kind, date, ids, rumored, slot}], спросить владельца [(strike, источников)], сверх лимита [ids])."""
    now = now or datetime.now(timezone.utc)
    entries = jread(LOG_F, [])
    done = {i for e in entries for i in e.get("ids", [])}
    asked = {e["asked"] for e in entries if "asked" in e}
    ok, ask = [], []
    for s in rows:
        sid = strike_id(s)
        if sid in done:
            continue
        if str(s.get("confidence", "reported")).lower() == "rumored" and sid not in approved:
            n = len(sources(s, deep))
            if n < 2:
                if sid not in asked:
                    ask.append((s, n))
                continue
            s = dict(s, _rumored=True)
        elif str(s.get("confidence", "reported")).lower() == "rumored":
            s = dict(s, _rumored=True)
        ok.append((sid, s))
    groups = []
    for sid, s in sorted(ok, key=lambda x: (str(x[1].get("date"))[:10], minute(x[1]) is None, minute(x[1]) or 0)):
        d, m = str(s.get("date"))[:10], minute(s)
        g = groups[-1] if groups and groups[-1]["date"] == d else None
        if g and (m is None or g["m0"] is None or m - g["m0"] <= MERGE_MIN):
            g["ids"].append(sid)
            g["rumored"] |= bool(s.get("_rumored"))
        else:
            groups.append({"date": d, "m0": m, "ids": [sid], "rumored": bool(s.get("_rumored"))})
    slots = [datetime.fromisoformat(e["slot"]) for e in entries if "slot" in e]
    last = max(slots, default=now - GAP)
    out, over = [], []
    for g in groups:
        slot = max(now, last + GAP)
        if sum(1 for t in slots if t > slot - timedelta(hours=24)) >= MAX_DAY:
            over += g["ids"]
            continue
        slots.append(slot)
        last = slot
        out.append({"kind": f"urgent-{g['ids'][0][:6]}", "date": g["date"], "ids": g["ids"],
                    "rumored": g["rumored"], "slot": slot.isoformat()})
    return out, ask, over


# ── запуск ───────────────────────────────────────────────────────────────────
def bot():
    try:
        return (Path("/root/.npz-bot/token").read_text().strip(), Path("/root/.npz-bot/chat_id").read_text().strip())
    except OSError:
        return None, None


def tg(method, **kw):
    t, _ = bot()
    if not t:
        return
    body = urllib.parse.urlencode({k: json.dumps(v) if isinstance(v, dict) else v for k, v in kw.items()}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{t}/{method}", body, timeout=20)
    except Exception as e:  # noqa: BLE001
        log(f"telegram: {e}")


def say(text, kb=None):
    _, c = bot()
    if c:
        tg("sendMessage", chat_id=c, text=text, disable_web_page_preview="true", **({"reply_markup": kb} if kb else {}))


def launch(job, by):
    wait = max(0, int((datetime.fromisoformat(job["slot"]) - datetime.now(timezone.utc)).total_seconds()))
    env = dict(os.environ, REEL_KIND=job["kind"], REEL_ONLY=",".join(job["ids"]),
               REEL_ALLOW_RUMORED="1" if job["rumored"] else "0")
    cmd = (f"sleep {wait}; cd {VIDEO} && flock -w 3600 /var/lock/npz-video.lock "
           f"nice -n 10 ./reel/daily.sh {job['date']} >> {REPO}/agents/logs/video.log 2>&1")
    subprocess.Popen(["bash", "-c", cmd], env=env, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"{job['kind']} {job['date']}: {len(job['ids'])} уд., старт через {wait // 60} мин"
        f"{' (слухи, ≥2 источника)' if job['rumored'] else ''} — {by}")


def dispatch(rows, by="молния", approved=(), dry=False):
    """Главный вход: strike_pipeline (молния), yt-watch (хроника), кнопка владельца. -> запуски."""
    with locked():
        jobs, ask, over = plan(rows, approved)
        if dry:
            return jobs, ask, over
        entries = jread(LOG_F, [])
        now = datetime.now(timezone.utc).isoformat()
        entries += [dict(j, by=by, created=now) for j in jobs]
        entries += [{"asked": strike_id(s), "created": now} for s, _ in ask]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        jwrite(LOG_F, [e for e in entries if e.get("created", now) >= cutoff])
    for j in jobs:
        launch(j, by)
    for s, n in ask:
        sid = strike_id(s)
        say(f"🎬 Слух, источник {n}: {s.get('date')} {s.get('city')} — {str(s.get('target') or '')[:90]}\n"
            f"{s.get('source_url') or ''}\nСрочный ролик с пометкой «не подтверждено»?",
            {"inline_keyboard": [[{"text": "🎬 Срочный ролик", "callback_data": f"urg_ok|{sid}"},
                                  {"text": "🚫 Нет", "callback_data": f"urg_no|{sid}"}]]})
    if over:
        log(f"лимит {MAX_DAY} срочных за 24 ч — {len(over)} уд. уйдут в сводку дня")
    return jobs, ask, over


def approve(sid):
    rows = [s for s in strikes() if strike_id(s) == sid]
    if not rows:
        return None
    jobs, _, over = dispatch(rows, by="кнопка владельца", approved={sid})
    return jobs[0] if jobs else ("over" if over else "done")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("plan", "run", "approve"):
        sys.exit(__doc__)
    ids = set(sys.argv[2].split(","))
    if sys.argv[1] == "approve":
        print(approve(sys.argv[2]))
        return
    rows = [s for s in strikes() if strike_id(s) in ids]
    jobs, ask, over = dispatch(rows, by="вручную", dry=sys.argv[1] == "plan")
    for j in jobs:
        print("запуск", j)
    for s, n in ask:
        print(f"спросить владельца (источников {n}):", strike_id(s), s.get("city"), s.get("target"))
    if over:
        print("сверх лимита:", over)


if __name__ == "__main__":
    main()
