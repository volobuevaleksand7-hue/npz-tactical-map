#!/usr/bin/env python3
"""check-future-dates.py — «время не врёт»: guard против дат/времени из будущего.

ЗАЧЕМ. 15.07.2026 агент записал удар по Балаклавской ТЭС как `2026-07-15 23:10`,
когда на часах было 13:44 МСК — событие «произошло» на 9 часов позже момента записи.
Реально удар был ночью 14.07. Модель текущего времени не знает, промпт его не даёт,
поэтому дату она берёт из головы. Ни санитайзер, ни pre-commit этого не ловили.

ДВА РАЗНЫХ СЛУЧАЯ — И ОБРАЩЕНИЕ С НИМИ РАЗНОЕ:

  1. Метаполя (generated_at/updated/fetched_at) — служебная метка «когда собрано».
     Фактом о мире не является, врёт постоянно и безобидно (generated_at=12:00
     при 11:17 UTC). ЧИНИМ на месте (clamp к now) — блокировать коммит из-за
     служебной метки значит глушить сбор данных на ровном месте.

  2. date/time записи — ФАКТ о мире. Чинить нельзя: правильного времени мы не
     знаем, а угадать — значит подделать. БЛОКИРУЕМ коммит, пусть разбирается
     человек. Удалять запись тоже нельзя — это усыхание архива (11.07: 172→67),
     см. sanitize-strikes.py.

Запуск:
  python3 agents/check-future-dates.py data/strikes.json   # из pre-commit
  python3 agents/check-future-dates.py --selfcheck         # проверка самой логики

Обход (осознанный бэкфилл): ALLOW_FUTURE_DATES=1.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))          # сайт живёт по МСК, время ударов — МСК
META_KEYS = ("generated_at", "updated", "fetched_at")
ARRAY_KEYS = ("strikes", "history")

# ponytail: запас в 2ч ловит грубую галлюцинацию (23:10 при 13:44 = +9ч), но не
# спорит с округлением источника. Нужна точность до минут — нужен источник времени
# у агента, а не порог тут.
TIME_SLACK_H = 2
META_SLACK_MIN = 5
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})")


def clamp_meta(d, now_utc):
    """Метки времени из будущего → now. Возвращает список (ключ, было, стало)."""
    fixed = []
    if not isinstance(d, dict):
        return fixed
    for k in META_KEYS:
        v = d.get(k)
        if not isinstance(v, str):
            continue
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if t > now_utc + timedelta(minutes=META_SLACK_MIN):
            new = now_utc.isoformat(timespec="seconds")
            d[k] = new
            fixed.append((k, v, new))
    return fixed


def future_records(arr, now_msk):
    """Записи с датой/временем из будущего. Возвращает список (запись, причина)."""
    today = now_msk.strftime("%F")
    bad = []
    for x in arr:
        if not isinstance(x, dict):
            continue
        ds = str(x.get("date", ""))[:10]
        if not DATE_RE.match(ds):
            continue
        if ds > today:
            bad.append((x, "дата %s ещё не наступила (сегодня %s МСК)" % (ds, today)))
            continue
        if ds != today:
            continue
        m = TIME_RE.match(str(x.get("time", "")))
        if not m:
            continue
        ev_min = int(m.group(1)) * 60 + int(m.group(2))
        cut_min = now_msk.hour * 60 + now_msk.minute + TIME_SLACK_H * 60
        # запас перевалил за полночь — сегодня уже нечему быть «слишком поздним»
        if cut_min < 24 * 60 and ev_min > cut_min:
            bad.append((x, "время %s сегодня ещё не наступило (сейчас %s МСК)"
                        % (x.get("time"), now_msk.strftime("%H:%M"))))
    return bad


def check(path, now_utc=None):
    """Чинит метаполя, ищет записи из будущего. Возвращает (n_fixed, bad_list)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(MSK)
    with open(path, encoding="utf-8") as f:
        d = json.load(f)

    # Метаполя чиним и на верхнем уровне, и во вложенном meta{} — fuel-state.json
    # держит generated_at именно в meta{} (был баг: fuel-state с generated_at из
    # будущего 23:59 просачивался, т.к. clamp_meta смотрел только топ-уровень, а
    # health по нему считал age=0 → маскировал протухание).
    fixed = clamp_meta(d, now_utc)
    if isinstance(d, dict) and isinstance(d.get("meta"), dict):
        fixed += clamp_meta(d["meta"], now_utc)
    if fixed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)

    bad = []
    arrs = [d] if isinstance(d, list) else [d[k] for k in ARRAY_KEYS if isinstance(d.get(k), list)]
    for arr in arrs:
        bad.extend(future_records(arr, now_msk))
    return fixed, bad


def selfcheck():
    """Одна runnable-проверка обеих веток на фиксированном «сейчас»."""
    import tempfile

    now = datetime(2026, 7, 15, 10, 44, tzinfo=timezone.utc)   # 13:44 МСК
    data = {
        "generated_at": "2026-07-15T23:45:00+00:00",           # +13ч → чиним
        "meta": {"generated_at": "2026-07-15T22:00:00+00:00"},  # вложенное (fuel-state) → тоже чиним
        "strikes": [
            {"date": "2026-07-14", "time": "ночь", "city": "Афипский"},      # ок
            {"date": "2026-07-15", "time": "09:10", "city": "прошедшее"},    # ок
            {"date": "2026-07-15", "time": "14:30", "city": "в пределах запаса"},  # ок
            {"date": "2026-07-15", "time": "23:10", "city": "Севастополь"},  # реальный баг
            {"date": "2026-07-16", "time": "ночь", "city": "завтра"},        # дата вперёд
        ],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        p = f.name

    fixed, bad = check(p, now_utc=now)
    keys = sorted(f[0] for f in fixed)
    assert keys == ["generated_at", "generated_at"], fixed  # топ + вложенное meta
    cities = sorted(x.get("city") for x, _ in bad)
    assert cities == ["Севастополь", "завтра"], cities
    out = json.load(open(p, encoding="utf-8"))
    assert out["generated_at"] == "2026-07-15T10:44:00+00:00"
    assert out["meta"]["generated_at"] == "2026-07-15T10:44:00+00:00", "вложенное meta.generated_at должно чиниться"
    assert len(out["strikes"]) == 5, "записи не удаляем"
    os.unlink(p)
    print("selfcheck OK: метаполя (топ+meta) починены, 2 записи из будущего пойманы, ничего не удалено")


def main():
    if "--selfcheck" in sys.argv:
        selfcheck()
        return 0
    if len(sys.argv) < 2:
        print("usage: check-future-dates.py <file.json> | --selfcheck", file=sys.stderr)
        return 2

    rc = 0
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            continue
        try:
            fixed, bad = check(path)
        except (ValueError, OSError) as e:
            print("check-future-dates: %s — не разобрать (%s), пропускаем" % (path, e), file=sys.stderr)
            continue

        for k, was, now in fixed:
            print("check-future-dates: %s — %s из будущего (%s) → %s" % (path, k, was, now),
                  file=sys.stderr)
        for x, why in bad:
            print("check-future-dates: BLOCKED — %s: %s | %s | %s"
                  % (path, why, x.get("city"), str(x.get("target", ""))[:50]), file=sys.stderr)
        if bad:
            rc = 1
    if rc and os.environ.get("ALLOW_FUTURE_DATES") == "1":
        print("check-future-dates: ALLOW_FUTURE_DATES=1 — пропускаем.", file=sys.stderr)
        return 0
    if rc:
        print("check-future-dates: события не могут произойти в будущем. Исправь дату/время"
              " по источнику (осознанный бэкфилл → ALLOW_FUTURE_DATES=1).", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
