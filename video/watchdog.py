#!/usr/bin/env python3
"""Сторож запусков видео (cron */10 на VPS). Следит ТОЛЬКО за видео-кронами:
  reel (06:15 UTC), reel-evening (16:15 UTC), weekly (вс 15:00 UTC).

Для каждого запуска проверяет три вещи:
  1. СТАРТ: после «старт+12 мин» в agents/logs/video.log есть строка «[ts] <kind> <дата>».
     Нет -> cron-MISSED (cron не сработал / упал до первой строки).
  2. ИТОГ: к дедлайну есть out/<kind>-<дата>.uploaded. Нет -> причина из хвоста лога:
     аудит не пройден / не собран / идёт слишком долго / нет итога. Причина «новых ударов нет»
     — не авария, тихо пропускается.
  3. СРЕДА: свободно на диске < 3 ГБ.
При проблеме: OPEN-инцидент в docs/agents/incidents.md (его читает Hermes — это и есть задача на
исправление) + одно сообщение в Telegram с причиной и уликами. Повторно об одном и том же не
пишет (video/.watchdog-state.json). Когда ролик всё-таки вышел — инцидент закрывается сам.
Запуск: watchdog.py [--dry-run] [--now YYYY-MM-DDTHH:MM] [--selfcheck]
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

VIDEO = Path(__file__).resolve().parent
ROOT = VIDEO.parent
LOG = ROOT / "agents" / "logs" / "video.log"
OUT = VIDEO / "out"
STATE = VIDEO / ".watchdog-state.json"
HEARTBEAT = VIDEO / ".watchdog-heartbeat"
MSK = timezone(timedelta(hours=3))
# kind, дни недели (0=пн, None=ежедневно), старт UTC, дедлайн итога UTC
SCHEDULE = [
    ("reel",         None, "06:15", "08:00"),
    ("reel-evening", None, "16:15", "18:30"),
    ("weekly",       6,    "15:00", "19:30"),
]
START_GRACE_MIN = 12
MIN_FREE_GB = 3.0
HEAD = re.compile(r"^\[(\d{4}-\d\d-\d\dT[\d:]+Z)\] (reel|reel-evening|weekly|urgent\S*) (\d{4}-\d\d-\d\d)\s*$")

_spec = importlib.util.spec_from_file_location("sw", ROOT / "agents" / "summary-watchdog.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)  # tg_send, _split, git_sync, now_msk
sw.LOG = ROOT / "agents" / "logs" / "video-watchdog.log"


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def segment(kind, day):
    """Строки лога одного запуска (от заголовка до следующего заголовка) -> (старт_ts|None, [строки])."""
    if not LOG.exists():
        return None, []
    with open(LOG, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 6_000_000))
        lines = f.read().decode("utf-8", "replace").splitlines()
    start, seg, inside = None, [], False
    for ln in lines:
        m = HEAD.match(ln)
        if m:
            inside = (m.group(2) == kind and m.group(3) == day)
            if inside and start is None:
                start = m.group(1)
            continue
        if inside:
            seg.append(ln)
    return start, seg


def running():
    r = subprocess.run(["pgrep", "-af", r"reel/daily\.sh|weekly/weekly\.sh|render_reel|build_reel|build_weekly"],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "pgrep" not in l and "watchdog" not in l]


def judge(kind, day, now_min, start_hm, dead_hm, seg_start, seg):
    """-> (reason|None, детали). reason: cron-missed | audit-failed | build-failed | too-slow | no-result."""
    if (OUT / f"{kind}-{day}.uploaded").exists():
        return None, "залит"
    text = "\n".join(seg)
    if "новых ударов нет, выпуск пропущен" in text:
        return None, "тихо пропущен: новых ударов нет"
    if "уже залит" in text:
        return None, "уже залит"
    if "аудит не пройден дважды" in text:
        fails = [l for l in seg if "audit FAIL" in l][:4]
        return "audit-failed", "\n".join(fails) or "аудит не пройден дважды"
    m = re.search(r"не собран \(rc=(\d+)\)", text)
    if m:
        return "build-failed", f"ролик не собран, rc={m.group(1)}"
    if seg_start is None:
        if now_min >= hm(start_hm) + START_GRACE_MIN:
            return "cron-missed", f"в video.log нет строки «{kind} {day}» — cron не стартовал"
        return None, "ещё не время"
    if now_min >= hm(dead_hm):
        if running():
            return "too-slow", "до дедлайна не вышел, процесс ещё идёт"
        return "no-result", "дедлайн прошёл, .uploaded нет, процессов нет"
    return None, "идёт"


def advice(reason, kind, day):
    base = {
        "cron-missed": [
            "`crontab -l | grep -n %s` — строка на месте? `systemctl status cron`, `grep CRON /var/log/syslog | tail`" % ("weekly" if kind == "weekly" else "daily.sh"),
            "запусти вручную в tmux (без pty рендер падает): `tmux new -d -s v \"cd /root/npz-tactical-map/video && %s\"`" % (
                "./weekly/weekly.sh" if kind == "weekly" else "REEL_KIND=%s ./reel/daily.sh" % kind),
        ],
        "audit-failed": [
            "прочитай в video.log блок «audit» за %s: если мало ударов (тихая ночь) — решить, нужен ли ролик" % day,
            "иначе чини причину (озвучка/клипы/длительность) и перезапусти `REEL_KIND=%s ./reel/daily.sh %s` в tmux" % (kind, day),
        ],
        "build-failed": ["найди «не собран» в video.log, исправь причину, перезапусти в tmux"],
        "too-slow": ["`pgrep -af daily.sh`, `df -h /`, `tail -50 agents/logs/video.log` — завис рендер/нет места/ждёт замок?"],
        "no-result": ["`tail -80 agents/logs/video.log`; проверь `df -h /`, `ls video/out`, замок /var/lock/npz-video.lock"],
        "disk-low": ["освободи место: `du -xh /root --max-depth=2 | sort -h | tail -20`; `video/cleanup.sh`; не трогать video/reel/cache/tts, /root/tts-models, data/"],
    }
    return base.get(reason, [])


def tg_text(reason, kind, day, detail, iid):
    head = {
        "cron-missed": "⛔ Видео-крон не запустился",
        "audit-failed": "🟠 Ролик не вышел: не прошёл проверку",
        "build-failed": "🟠 Ролик не собран",
        "too-slow": "🟡 Ролик не вышел вовремя (ещё идёт)",
        "no-result": "🟠 Ролик не вышел, причина неясна",
        "disk-low": "🟠 На сервере мало места",
    }[reason]
    return f"{head}\n{kind} · {day}\n{detail[:600]}\n\nЗадача на исправление: {iid} (docs/agents/incidents.md)"


def incident_block(iid, reason, kind, day, detail):
    steps = "\n".join("- " + s for s in advice(reason, kind, day))
    return (f"## [OPEN] {iid}\nstatus: OPEN\nopened: {sw.now_msk()} — video-watchdog\n"
            f"{kind} за {day}: {reason}. {detail}\nЧто сделать:\n{steps}\n\n")


def update_incidents(want, closed_ids, dry):
    """want: {iid: block}; closed_ids: iid, которые можно закрыть. -> изменён ли файл."""
    p = sw.INCIDENTS
    if not p.exists():
        return False
    head, blocks = sw._split(p.read_text())
    open_ids = {b[1] for b in blocks if b[0] == "OPEN"}
    changed = False
    for b in blocks:
        if b[0] == "OPEN" and b[1] in closed_ids:
            b[0] = "RESOLVED"
            b[2] = (b[2].replace("## [OPEN] ", "## [RESOLVED] ", 1).replace("status: OPEN", "status: RESOLVED", 1)
                    + f"resolved: {sw.now_msk()} — ролик вышел (авто, video-watchdog)\n")
            changed = True
    new = [["OPEN", i, blk] for i, blk in want.items() if i not in open_ids]
    if new:
        changed = True
    if changed and not dry:
        p.write_text(head + "\n\n" + "".join(b[2] for b in new + blocks).rstrip() + "\n")
    return changed


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def run(now, dry):
    day, now_min = now.strftime("%Y-%m-%d"), now.hour * 60 + now.minute
    state, want, closed, msgs = load_state(), {}, set(), []
    for kind, wd, start_hm, dead_hm in SCHEDULE:
        if wd is not None and now.weekday() != wd:
            continue
        if now_min < hm(start_hm):
            continue
        seg_start, seg = segment(kind, day)
        reason, detail = judge(kind, day, now_min, start_hm, dead_hm, seg_start, seg)
        iid = f"video-{kind}-{day}"
        if reason is None:
            if detail in ("залит",):
                closed.add(iid)
            continue
        want[iid] = incident_block(iid, reason, kind, day, detail)
        key = f"{iid}:{reason}"
        if key not in state:
            msgs.append((key, tg_text(reason, kind, day, detail, iid)))
    free = shutil.disk_usage("/").free / 2**30
    if free < MIN_FREE_GB:
        iid, key = f"video-disk-{day}", f"video-disk-{day}:disk-low"
        want[iid] = incident_block(iid, "disk-low", "сервер", day, f"свободно {free:.1f} ГБ")
        if key not in state:
            msgs.append((key, tg_text("disk-low", "сервер", day, f"свободно {free:.1f} ГБ (рендеру нужно ~3 ГБ)", iid)))
    changed = update_incidents(want, closed, dry)
    for key, text in msgs:
        print("TG:", text.replace("\n", " | "))
        if not dry and sw.tg_send(text):
            state[key] = now.isoformat()
    if not dry:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
        HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())
        if changed:
            sw.git_sync("incidents: video-watchdog " + day)
    print(f"{now:%F %H:%M} UTC: проверено, проблем {len(want)}, сообщений {len(msgs)}, свободно {free:.1f} ГБ")
    return 0


def selfcheck():
    # 1) заголовок лога
    assert HEAD.match("[2026-10-11T06:15:01Z] reel 2026-10-11")
    assert not HEAD.match("[2026-10-11T06:15:01Z] ok /x")
    # 2) judge: cron не стартовал
    r, _ = judge("reel", "2026-10-11", hm("06:40"), "06:15", "08:00", None, [])
    assert r == "cron-missed", r
    r, _ = judge("reel", "2026-10-11", hm("06:20"), "06:15", "08:00", None, [])
    assert r is None
    # 3) аудит
    r, d = judge("reel", "2099-01-01", hm("07:00"), "06:15", "08:00", "x",
                 ["audit FAIL: длительность 14 с", "reel: аудит не пройден дважды — пропущены"])
    assert r == "audit-failed" and "14" in d, (r, d)
    # 4) тихий день и «в процессе»
    r, _ = judge("reel", "2099-01-01", hm("07:00"), "06:15", "08:00", "x", ["reel: reel 2099 — новых ударов нет, выпуск пропущен"])
    assert r is None
    # 5) дедлайн без итога
    r, _ = judge("reel", "2099-01-01", hm("09:00"), "06:15", "08:00", "x", ["что-то"])
    assert r in ("no-result", "too-slow")
    print("selfcheck OK")
    return 0


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    n = datetime.now(timezone.utc)
    if "--now" in sys.argv:
        n = datetime.fromisoformat(sys.argv[sys.argv.index("--now") + 1]).replace(tzinfo=timezone.utc)
    sys.exit(run(n, "--dry-run" in sys.argv))
