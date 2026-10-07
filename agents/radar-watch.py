#!/usr/bin/env python3
"""Радар → внеплановая проверка ударов (07.10.2026).

Радар (radar-map.ru) видит атаку раньше новостей: «Работа ПВО», «Сбитие БПЛА»,
«взрывы» над городом приходят в ленту в момент атаки, а сообщения о поражённом
объекте — через 1–6 часов. Сборщик ударов при этом ходит только в 04:35 и 16:35
UTC, поэтому удар по НПЗ ночью попадал на карту к утру, а то и к вечеру.

Скрипт идёт после каждого обновления радара (hermes/cron-radar-refresh.sh, */10):
  1. берёт города радара (data/radar-state.json → cities[], у каждого
     координаты и последнее сообщение) и ищет активность ПВО/взрывы в радиусе
     NEAR_KM от НПЗ или терминала из data/fuel-state.json;
  2. заводит тревогу на объект: первый сигнал, последний сигнал, тексты;
  3. через CHECK_DELAYS после первого сигнала запускает сборщик ударов вне
     расписания с подсказкой «радар видел атаку на X — проверь в первую
     очередь». Найденный удар дальше идёт обычным путём: strike_pipeline
     (:07/:27/:47) → молния в канал → срочный рилс;
  4. тревога закрывается, как только в strikes.json появился удар рядом с
     объектом, или после последней проверки.

Сам strikes.json скрипт не трогает и в канал ничего не пишет: радар даёт
сигнал, а подтверждение остаётся за сборщиком и его правилами источников.

Выключатель: NPZ_RADAR_WATCH=0. Пробный прогон без запуска агента: --dry-run.
"""
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADAR = os.path.join(ROOT, "data", "radar-state.json")
FUEL = os.path.join(ROOT, "data", "fuel-state.json")
STRIKES = os.path.join(ROOT, "data", "strikes.json")
PROMPT = os.path.join(ROOT, "agents", "update-prompt-strikes.md")
STATE = os.environ.get("NPZ_RADAR_WATCH_STATE", "/root/.npz-radar-watch.json")
LOG = os.path.join(ROOT, "agents", "logs", "cron.log")

NEAR_KM = 25           # город радара ↔ объект
STRIKE_NEAR_KM = 35    # удар в strikes.json закрывает тревогу
FRESH_SEC = 3 * 3600   # сообщение радара старше — не сигнал
CHECK_DELAYS = (40 * 60, 150 * 60, 330 * 60)   # проверки после первого сигнала
MIN_GAP_SEC = 45 * 60  # не чаще одного внепланового прогона
CLOSE_AFTER = 8 * 3600

# «Опасность по БПЛА» и «Фиксация» — это тревога, а не атака; сигнал — только
# работа ПВО по городу, сбитие или взрывы/пожар.
SIGNAL_RE = re.compile(r"работа\s+пво|работает\s+пво|сбити|сбивают|взрыв|прил[её]т|пожар|хлопк|детонац|задымлен",
                       re.IGNORECASE)
MSK = timezone(timedelta(hours=3))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def km(lat1, lon1, lat2, lon2):
    p = math.radians
    a = (math.sin(p(lat2 - lat1) / 2) ** 2
         + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def objects():
    fs = load(FUEL, {})
    out = []
    for o in fs.get("refineries", []) + fs.get("export_terminals", []):
        if o.get("lat") is not None and o.get("lon") is not None:
            out.append({"name": o["name"], "lat": o["lat"], "lon": o["lon"]})
    return out


def signals(radar, objs, now):
    """[(объект, город, ts, текст)] — свежая активность ПВО рядом с объектом."""
    out = []
    for c in radar.get("cities", []):
        ts = c.get("last_event_ts") or 0
        text = (c.get("source_text") or "").strip()
        if now - ts > FRESH_SEC or not SIGNAL_RE.search(text):
            continue
        if c.get("lat") is None:
            continue
        near = [(km(c["lat"], c["lon"], o["lat"], o["lon"]), o) for o in objs]
        near = [x for x in near if x[0] <= NEAR_KM]
        if not near:
            continue
        o = min(near, key=lambda x: x[0])[1]
        out.append((o, c.get("name", ""), ts, " ".join(text.split())[:240]))
    return out


def strike_near(obj, since_date):
    s = load(STRIKES, {})
    items = s if isinstance(s, list) else s.get("strikes", [])
    for x in items:
        if (x.get("date") or "") < since_date or x.get("lat") is None:
            continue
        if km(x["lat"], x["lon"], obj["lat"], obj["lon"]) <= STRIKE_NEAR_KM:
            return x
    return None


def focus_prompt(alerts):
    lines = []
    for a in alerts:
        first = datetime.fromtimestamp(a["first_ts"], MSK).strftime("%d.%m %H:%M")
        cities = ", ".join(sorted(set(a["cities"])))
        lines.append(f"- {a['object']} (радар: {cities}, с {first} МСК): «{a['texts'][-1]}»")
    base = open(PROMPT, encoding="utf-8").read()
    return base + (
        "\n\n## ⚡ ВНЕПЛАНОВЫЙ ПРОГОН ПО СИГНАЛУ РАДАРА\n\n"
        "Радар воздушной обстановки (radar-map.ru) только что показал работу ПВО / взрывы "
        "рядом с объектами ниже. Радар — это сигнал, не подтверждение: ищи в первую очередь "
        "сообщения о поражении ИМЕННО этих объектов за последние 12 часов (власти региона, "
        "местные СМИ и каналы, федеральные СМИ). Нашёл подтверждение по правилам выше — "
        "добавь удар как обычно. Не нашёл — НЕ добавляй ничего по одному радару, "
        "работа ПВО сама по себе ударом не считается.\n\n" + "\n".join(lines) + "\n"
    )


def launch(alerts, dry):
    tmp = f"/tmp/npz-radar-focus-{int(time.time())}.md"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(focus_prompt(alerts))
    names = ", ".join(a["object"] for a in alerts)
    if dry:
        print(f"radar-watch: [dry-run] запустил бы сборщик ударов: {names} ({tmp})")
        return
    env = dict(os.environ, NPZ_LOCK_WAIT="900")
    cmd = (f"cd {ROOT} && ./agents/run-agent.sh {tmp} strikes-radar >> {LOG} 2>&1; "
           f"rm -f {tmp}")
    subprocess.Popen(["bash", "-c", cmd], env=env, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"radar-watch: → внеплановый сборщик ударов: {names}")


def main():
    dry = "--dry-run" in sys.argv
    if os.environ.get("NPZ_RADAR_WATCH", "1") == "0":
        return
    now = int(time.time())
    radar = load(RADAR, {})
    state = load(STATE, {"alerts": {}, "last_launch": 0})
    alerts = state["alerts"]
    objs = objects()

    for o, city, ts, text in signals(radar, objs, now):
        a = alerts.get(o["name"])
        if a and (a["status"] == "open" or now - a["last_ts"] < CLOSE_AFTER):
            if ts > a["last_ts"]:
                a["last_ts"] = ts
                if text not in a["texts"]:
                    a["texts"] = (a["texts"] + [text])[-5:]
            if city not in a["cities"]:
                a["cities"].append(city)
            continue
        alerts[o["name"]] = {"object": o["name"], "lat": o["lat"], "lon": o["lon"],
                             "first_ts": ts, "last_ts": ts, "cities": [city],
                             "texts": [text], "checks": 0, "status": "open"}
        print(f"radar-watch: тревога {o['name']} ← {city}: {text[:120]}")

    due = []
    since = (datetime.now(MSK) - timedelta(days=1)).strftime("%Y-%m-%d")
    for name, a in list(alerts.items()):
        if a["status"] != "open":
            if now - a["last_ts"] > 2 * CLOSE_AFTER:
                del alerts[name]
            continue
        hit = strike_near(a, since)
        if hit:
            a["status"] = "found"
            print(f"radar-watch: {name} — удар на карте: {hit.get('title') or hit.get('target')}")
            continue
        if a["checks"] >= len(CHECK_DELAYS):
            if now - a["last_ts"] > CLOSE_AFTER:
                a["status"] = "closed"
            continue
        if now - a["first_ts"] >= CHECK_DELAYS[a["checks"]]:
            due.append(a)

    if due and now - state.get("last_launch", 0) >= MIN_GAP_SEC:
        launch(due, dry)
        if not dry:
            for a in due:
                a["checks"] += 1
            state["last_launch"] = now

    if not dry:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
