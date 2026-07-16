#!/usr/bin/env python3
"""Watchdog: читает generated_at всех живых data/*.json, сравнивает с порогом
(≈2× cron-интервала агента) и пишет data/health.json. Если файл просрочен —
помечает stale. Фронт может показать «N агентов отстали». Запуск из cron-рутины.

Поддержка heartbeat: если data/heartbeats.json существует, для каждого файла
считается heartbeat_age_hours и статус уточняется:
  ok          — данные свежи
  stale_alive — данные просрочены, но heartbeat свеж (агент работал, просто нет новостей)
  stale_dead  — данные просрочены и heartbeat просрочен/отсутствует (агент мёртв)
  unknown     — generated_at не найден
"""
import json, os, datetime, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Непушенные коммиты старше этого = публикация встала (данные не доходят до сайта).
# Агенты пушут постоянно (radar */10мин), поэтому даже 1.5ч задержки — аномалия,
# но запас гасит короткие сетевые заминки. См. publish_status().
PUBLISH_LAG_THRESHOLD_H = 1.5

# файл -> (агент, порог свежести данных в часах, heartbeat-key, порог свежести heartbeat в часах).
# heartbeat-key совпадает с label в run-agent.sh.
#
# hb_fresh_h — окно «агент на связи»: ≈2x его cron-интервала + буфер. Держать в
# синхроне с crontab, иначе watchdog слепнет. До 15.07 здесь по всему флоту
# стояло 72ч: docs/heartbeat-plan.md обосновывал их тем, что «agents run at most
# daily», хотя в кроне давно 6-часовые рутины. Цена ошибки — 15.07 флот лежал 19ч
# на протухшем OAuth, а баннер показывал «1 агент не на связи» вместо десяти.
# Фактический крон: 0,6,12,18 -> 6ч; fuel-availability */4; fuel-voices */8;
# radar */10мин; forecast/economy — ЕЖЕДНЕВНО 03:30/04:30 (доки врут про «weekly»).
# Статичные файлы (azs-*, geojson) не проверяем.
# Список, а не dict: файл больше НЕ уникальный ключ — data/fuel-state.json пишут
# ДВА агента (npz-status — статусы НПЗ; fuel-market — рыночная часть), и следить
# надо за каждым. Строка = (файл, агент, порог данных ч | None, hb-key, окно hb ч).
WATCH = [
    ("strikes.json",           "npz-data (strikes)",   18, "strikes",           15),
    ("fuel-state.json",        "npz-data (npz)",        24, "npz-status",        15),
    ("history-crimea.json",    "npz-data (history)",    36, "history-crimea",    15),
    ("roads.json",             "npz-data (roads)",      36, "roads",             15),
    ("fuel-availability.json", "fuel-availability",     18, "fuel-availability", 10),
    ("fuel-voices.json",       "fuel-voices",           24, "fuel-voices",       20),
    ("grid-state.json",        "grid-status",           18, "grid-status",       15),
    ("radar-state.json",       "radar-state",          0.5, "radar-state",        2),
    ("forecast.json",          "forecast-economy",     200, "forecast",          50),
    ("economy.json",           "forecast-economy",     200, "economy",           50),
    # thr=None — у агента НЕТ своего файла: он пишет секцию чужого, и свежесть
    # этого файла ему приписать нельзя (её бампает сосед). Следим только за связью.
    # Именно fuel-market 15.07 маскировал мёртвый npz-status, обновляя generated_at
    # общего fuel-state.json: данные выглядели свежими на 2.3ч при агенте,
    # молчавшем 21.5ч. Cron: 15 0,6,12,18 (6ч) -> окно 15ч.
    ("fuel-state.json",        "fuel-market",         None, "fuel-market",       15),
]

# Дефолт для агентов, по которым per-file порог не задан.
HEARTBEAT_FRESHNESS_HOURS = 72


def gen_at(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    m = d.get("meta", {})
    ts = m.get("generated_at") or d.get("generated_at") or d.get("fetched_at") or d.get("last_event_at")
    if ts:
        return ts
    raw_ts = d.get("timestamp")
    if isinstance(raw_ts, (int, float)):
        return datetime.datetime.fromtimestamp(raw_ts, datetime.timezone.utc).isoformat()
    return d.get("date")


def parse(ts):
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        pass
    try:
        return datetime.datetime.strptime(str(ts)[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def load_heartbeats():
    path = os.path.join(ROOT, "data", "heartbeats.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def classify(data_age_h, thr_h, hb_age_h, hb_fresh_h):
    """Две ОРТОГОНАЛЬНЫЕ оси: свежесть ДАННЫХ и связь с АГЕНТОМ.

    Возвращает (status, data_stale, agent_dead).

    Ключевая правка 15.07: раньше «агент молчит» повышалось до stale_dead ТОЛЬКО
    если данные уже протухли. Пока данные в пороге (18-36ч), мёртвый агент молча
    числился "ok" — и авария на 19ч осталась невидимой. Свежесть данных не
    доказывает, что агент жив: соседний bulk-коммит мог обновить generated_at.
    """
    hb_dead = hb_age_h is None or hb_age_h > hb_fresh_h
    if thr_h is None:
        # агент без собственного файла (пишет секцию чужого) — только связь
        return ("dead" if hb_dead else "ok"), False, hb_dead
    if data_age_h is None:
        return "unknown", False, False
    data_stale = data_age_h > thr_h
    if data_stale:
        # данные старые, но агент отчитался -> просто нет новостей, не алертим
        return ("stale_dead" if hb_dead else "stale_alive"), True, hb_dead
    return ("dead" if hb_dead else "ok"), False, hb_dead


def selfcheck():
    # данные свежие, агент на связи
    assert classify(1, 18, 1, 15)[0] == "ok"
    # данные свежие, агент молчит -> раньше молча "ok", теперь видно
    assert classify(1, 18, 40, 15)[0] == "dead"
    assert classify(1, 18, None, 15)[0] == "dead"
    # данные протухли, агент на связи -> новостей нет, это не авария
    assert classify(20, 18, 1, 15)[0] == "stale_alive"
    # данные протухли И агент молчит
    assert classify(20, 18, 40, 15)[0] == "stale_dead"
    # нет generated_at
    assert classify(None, 18, 1, 15)[0] == "unknown"
    # регрессия 15.07: strikes 6.7ч (в пороге 18ч), агент мёртв 19ч при окне 15ч
    assert classify(6.7, 18, 19, 15) == ("dead", False, True)
    # forecast: ежедневная рутина, 30ч данных при пороге 200ч и окне 50ч — норма
    assert classify(30, 200, 21, 50) == ("ok", False, False)
    # агент без своего файла (thr=None) — судим ТОЛЬКО по связи, возраст данных
    # чужого файла ни на что не влияет (его бампает сосед)
    assert classify(0.1, None, 1, 15) == ("ok", False, False)
    assert classify(0.1, None, 40, 15) == ("dead", False, True)
    assert classify(999, None, 1, 15) == ("ok", False, False)
    # каждая строка WATCH распаковывается и hb-key уникален
    assert all(len(row) == 5 for row in WATCH)
    hb_keys = [row[3] for row in WATCH]
    assert len(hb_keys) == len(set(hb_keys)), "дублирующийся heartbeat-key в WATCH"
    print("healthcheck selfcheck: ok (%d агентов)" % len(WATCH))


def publish_status(now):
    """Доходят ли локальные коммиты до origin. До 16.07 health.json смотрел ТОЛЬКО
    локальные mtime данных — 15.07 публикация встала на ~6ч (грязное дерево
    publish-vps блокировало git-sync всех агентов): данные были свежими локально,
    сайт кормился origin'ом 6-8ч давности, а watchdog печатал healthy. Теперь
    сверяем HEAD с origin/main: сколько коммитов не запушено и как стар самый старый.
    Возвращает (unpushed:int|None, lag_h:float|None, stuck:bool|None).
    None = git/сеть недоступны — не роняем watchdog, помечаем публикацию unknown."""
    def git(*a):
        return subprocess.run(("git",) + a, cwd=ROOT,
                              capture_output=True, text=True, timeout=30)
    try:
        git("fetch", "origin", "main", "-q")
        r = git("rev-list", "--count", "origin/main..HEAD")
        unpushed = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
        if unpushed == 0:
            return 0, 0.0, False
        # committer-time самого старого непушенного коммита -> возраст задержки
        r = git("log", "origin/main..HEAD", "--format=%ct")
        cts = [int(x) for x in r.stdout.split()]
        lag_h = round((now.timestamp() - min(cts)) / 3600, 1) if cts else None
        stuck = lag_h is not None and lag_h > PUBLISH_LAG_THRESHOLD_H
        return unpushed, lag_h, stuck
    except Exception:
        return None, None, None


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    unpushed, publish_lag_h, publish_stuck = publish_status(now)
    heartbeats = load_heartbeats()
    files = []
    stale_count = 0
    dead_count = 0
    for fn, agent, thr_h, hb_key, hb_fresh_h in WATCH:
        ts = gen_at(os.path.join(ROOT, "data", fn))
        dt = parse(ts)
        # Клипуем отрицательный возраст: агент может писать generated_at на минуты
        # впереди часов watchdog (clock skew) — это не «будущее».
        data_age_h = None if dt is None else max(0.0, round((now - dt).total_seconds() / 3600, 1))

        hb_ts = heartbeats.get(hb_key)
        hb_dt = parse(hb_ts)
        hb_age_h = None if hb_dt is None else max(0.0, round((now - hb_dt).total_seconds() / 3600, 1))

        status, data_stale, hb_stale = classify(data_age_h, thr_h, hb_age_h, hb_fresh_h)
        if data_stale:
            stale_count += 1
        if hb_stale:
            dead_count += 1

        files.append({
            "file": fn, "agent": agent, "generated_at": ts,
            "age_hours": data_age_h, "data_age_hours": data_age_h,
            "threshold_hours": thr_h,
            "heartbeat_at": hb_ts, "heartbeat_age_hours": hb_age_h,
            "heartbeat_threshold_hours": hb_fresh_h,
            "heartbeat_stale": hb_stale,
            "status": status,
        })

    health = {
        "meta": {
            # Контракт (обновлён 15.07): dead_count = агенты, которые НЕ ВЫШЛИ НА СВЯЗЬ
            # (heartbeat протух/отсутствует) — независимо от возраста их данных.
            # Раньше он считал только stale_dead, т.е. требовал, чтобы данные ТОЖЕ
            # успели протухнуть; из-за этого мёртвый 19ч флот с ещё-свежими данными
            # показывал «1 агент не на связи» вместо десяти. Баннер в app.js:589
            # печатает именно dead_count и подписан «не на связи» — теперь совпадает.
            "checked_at": now.strftime("%Y-%m-%dT%H:%MZ"),
            "overall": "degraded" if (dead_count or publish_stuck) else "healthy",
            "stale_count": stale_count,
            "dead_count": dead_count,
            "heartbeat_dead_count": dead_count,  # back-compat: то же, что dead_count
            # Публикация: свежесть данных ЛОКАЛЬНО ≠ данные доехали до сайта.
            # publish_stuck=None -> git/сеть недоступны, статус неизвестен.
            "unpushed_commits": unpushed,
            "publish_lag_hours": publish_lag_h,
            "publish_stuck": bool(publish_stuck),
            "total": len(WATCH),
        },
        "files": files,
    }
    out = os.path.join(ROOT, "data", "health.json")
    json.dump(health, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("health: %s | stale %d/%d | dead %d | hb_dead %d" % (
        health["meta"]["overall"], stale_count, len(WATCH), dead_count, dead_count))
    if publish_stuck:
        print("  🚫 ПУБЛИКАЦИЯ ВСТАЛА: %d коммит(ов) не запушено, старейший %s ч — origin (сайт) отстаёт" % (
            unpushed, publish_lag_h))
    elif publish_stuck is None:
        print("  ? publish-check: git/сеть недоступны — статус публикации неизвестен")
    for f in files:
        if f["status"] != "ok":
            print("  ⚠ %s (%s): %s, data_age=%s h, hb_age=%s h" % (
                f["file"], f["agent"], f["status"],
                f["age_hours"], f["heartbeat_age_hours"]))
        elif f["heartbeat_stale"]:
            print("  💀 %s (%s): data ok but heartbeat DEAD, data_age=%s h, hb_age=%s h" % (
                f["file"], f["agent"],
                f["age_hours"], f["heartbeat_age_hours"]))


if __name__ == "__main__":
    import sys
    selfcheck() if "--selfcheck" in sys.argv else main()
