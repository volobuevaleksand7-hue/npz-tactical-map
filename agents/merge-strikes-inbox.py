#!/usr/bin/env python3
"""merge-strikes-inbox.py — вливает найденное агентом в полный архив ударов.

ЗАЧЕМ. `data/strikes.json` — 3200+ строк / 264K, а Read отдаёт агенту 2000 строк.
Архив он целиком НЕ ВИДИТ, но инструмент у него один — Write, то есть перезапись
файла ЦЕЛИКОМ. Промпт просил «запиши целиком» и тут же «никогда не удаляй старые» —
невыполнимое требование. Итог: 4 усыхания архива (11.07: 172→67, 12.07: 75→2,
15.07: 197→55 — последнее поймано вживую). Guard блокировал коммит, то есть архив
выживал, но и НОВЫЕ удары не доезжали — сбор стоял.

РЕШЕНИЕ. Агент пишет только НОВОЕ в маленький `strikes-inbox.json` (Write по силам),
а полный архив правит этот скрипт — без LLM, детерминированно. Дубли отсекает он же,
поэтому агенту не нужно видеть весь архив: ему хватает хвоста в `strikes-recent.json`.

Запуск:
  python3 agents/merge-strikes-inbox.py            # влить inbox → архив, обновить хвост
  python3 agents/merge-strikes-inbox.py --refresh  # только пересобрать хвост
  python3 agents/merge-strikes-inbox.py --selfcheck
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(REPO, "data", "strikes.json")
INBOX = os.path.join(REPO, "data", "strikes-inbox.json")
RECENT = os.path.join(REPO, "data", "strikes-recent.json")

RECENT_DAYS = 10          # хвост для агента: видеть, что уже записано, и не дублировать
MSK = timezone(timedelta(hours=3))


def key(x):
    """Ключ дедупа. id — если есть; иначе date+city+time+target (см. рецепт восстановления)."""
    if x.get("id"):
        return ("id", str(x["id"]).strip().lower())
    return (
        str(x.get("date", "")).strip(),
        str(x.get("city", "")).strip().lower(),
        str(x.get("time", "")).strip().lower(),
        str(x.get("target", "")).strip().lower()[:60],
    )


def _same_event(a, b):
    """Одно ли это событие: совпали КОГДА и ГДЕ (date+city+time). Формулировку target
    не сверяем — у re-report того же удара она переписана. Нужно только чтобы отличить
    «дубль» от «подозрительной коллизии id» для предупреждения в merge()."""
    return all(str(a.get(f, "")).strip().lower() == str(b.get(f, "")).strip().lower()
               for f in ("date", "city", "time"))


def load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


def as_list(d):
    """inbox допускаем и голым списком, и {"strikes": [...]} — агенты пишут по-разному."""
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("strikes", "new", "items"):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def merge(archive, incoming):
    """Возвращает (архив, добавлено, пропущено_дублей). Архив только РАСТЁТ."""
    strikes = archive.setdefault("strikes", [])
    seen = {}                       # key -> уже лежащая запись (для сверки события при коллизии)
    for x in strikes:
        if isinstance(x, dict):
            seen.setdefault(key(x), x)
    added = dupes = 0
    for x in incoming:
        if not isinstance(x, dict) or not str(x.get("date", "")).strip():
            continue
        k = key(x)
        prev = seen.get(k)
        if prev is not None:
            dupes += 1
            # DROP по id-коллизии — верный дефолт: один удар из двух источников (молния
            # strike-pipeline + newswatch) часто получает ОДИН id, и схлопывается только
            # так (target/time у них расходятся, составной ключ их бы не поймал).
            # НО у совпавших id могут разойтись date/city/time — тогда есть шанс, что это
            # РАЗНЫЙ удар, которому коллектор не инкрементил суффикс (см. 3 пары 10.07).
            # Не роняем молча — громко предупреждаем, чтобы человек проверил и при нужде
            # дал суффикс -2 вручную. ponytail: авто-bump тут НЕЛЬЗЯ — он бы расщепил
            #   частый дубль-двух-источников в фантом; лог — безопасный минимум.
            if k[0] == "id" and not _same_event(prev, x):
                print("merge-inbox: ⚠ подозрительная коллизия id %r — отброшен возможный "
                      "РАЗНЫЙ удар [%s/%s/%s] vs лежащий [%s/%s/%s]; если это другой "
                      "удар — дай суффикс -2 вручную"
                      % (prev.get("id"),
                         x.get("date"), x.get("city"), x.get("time"),
                         prev.get("date"), prev.get("city"), prev.get("time")),
                      file=sys.stderr)
            continue
        seen[k] = x
        strikes.append(x)
        added += 1
    # total рассинхронивался (196 при 197 записях): санитайзер его не пересчитывает.
    # Остальные поля summary не трогаем — их семантика на совести коллекторов.
    if isinstance(archive.get("summary"), dict):
        archive["summary"]["total"] = len(strikes)
    if added:
        archive["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return archive, added, dupes


# Хвост — ИНДЕКС для дедупа, а не копия данных. Полные записи с detail на 10 дней
# дают 1525 строк при лимите Read в 2000 — упрётся через неделю роста. Агенту, чтобы
# понять «это уже записано», хватает date/time/city/target.
RECENT_FIELDS = ("date", "time", "city", "region", "target", "confidence")


def build_recent(archive, days=RECENT_DAYS, now=None):
    """Хвост для агента: компактный индекс, гарантированно влезает в Read."""
    now = now or datetime.now(timezone.utc).astimezone(MSK)
    cutoff = (now - timedelta(days=days)).strftime("%F")
    recent = [{k: x[k] for k in RECENT_FIELDS if k in x}
              for x in archive.get("strikes", [])
              if isinstance(x, dict) and str(x.get("date", ""))[:10] >= cutoff]
    return {
        "_comment": ("ХВОСТ-ИНДЕКС архива за %d дней — только для чтения агентом, только "
                     "ключевые поля (полные записи — в data/strikes.json, его правит "
                     "agents/merge-strikes-inbox.py). Новые удары писать в "
                     "data/strikes-inbox.json." % days),
        "since": cutoff,
        "count": len(recent),
        "strikes": recent,
    }


def main():
    if "--selfcheck" in sys.argv:
        return selfcheck()

    archive = load(ARCHIVE, None)
    if not isinstance(archive, dict) or not isinstance(archive.get("strikes"), list):
        print("merge-inbox: %s не читается или не тот формат — выходим" % ARCHIVE, file=sys.stderr)
        return 1
    before = len(archive["strikes"])

    added = dupes = 0
    if "--refresh" not in sys.argv:
        incoming = as_list(load(INBOX, []))
        if incoming:
            archive, added, dupes = merge(archive, incoming)
            if added:
                with open(ARCHIVE, "w", encoding="utf-8") as f:
                    json.dump(archive, f, ensure_ascii=False, indent=1)
            # inbox чистим всегда: он разовый, иначе дубли поедут в следующий прогон
            with open(INBOX, "w", encoding="utf-8") as f:
                json.dump([], f)
            print("merge-inbox: влито %d, дублей пропущено %d, архив %d → %d"
                  % (added, dupes, before, len(archive["strikes"])), file=sys.stderr)
        else:
            print("merge-inbox: inbox пуст — нечего вливать", file=sys.stderr)

    # total дрейфует и без нас (санитайзер его не пересчитывает, ручные правки тоже):
    # застали 196 при 197 записях. Чиним всегда, а не только при вливании — но пишем
    # файл лишь при реальном расхождении, чтобы не плодить пустые коммиты.
    summ = archive.get("summary")
    if isinstance(summ, dict) and summ.get("total") != len(archive["strikes"]) and not added:
        print("merge-inbox: summary.total рассинхронен (%s → %d) — пересчитан"
              % (summ.get("total"), len(archive["strikes"])), file=sys.stderr)
        summ["total"] = len(archive["strikes"])
        with open(ARCHIVE, "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=1)

    with open(RECENT, "w", encoding="utf-8") as f:
        json.dump(build_recent(archive), f, ensure_ascii=False, indent=1)

    # Архив не должен уменьшаться НИКОГДА — это последний рубеж перед guard-ом.
    assert len(archive["strikes"]) >= before, "архив усох: %d → %d" % (before, len(archive["strikes"]))
    return 0


def selfcheck():
    global ARCHIVE, INBOX, RECENT

    # main() читает sys.argv — оставим ему пустой, иначе он снова уйдёт в selfcheck
    sys.argv = [sys.argv[0]]

    tmp = os.path.join("/tmp", "merge-selfcheck-%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)
    ARCHIVE = os.path.join(tmp, "strikes.json")
    INBOX = os.path.join(tmp, "strikes-inbox.json")
    RECENT = os.path.join(tmp, "strikes-recent.json")

    arch = {
        "strikes": [
            {"id": "old-1", "date": "2026-07-01", "city": "Рязань", "target": "НПЗ"},
            {"date": "2026-07-14", "time": "ночь", "city": "Афипский", "target": "НПЗ"},
        ],
        "summary": {"total": 999},           # рассинхрон — должен пересчитаться
        "generated_at": "2026-07-14T00:00:00+00:00",
    }
    json.dump(arch, open(ARCHIVE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump([
        {"id": "new-1", "date": "2026-07-15", "city": "Чёрное море", "target": "танкеры"},
        {"id": "old-1", "date": "2026-07-01", "city": "Рязань", "target": "НПЗ"},        # дубль по id
        {"date": "2026-07-14", "time": "ночь", "city": "Афипский", "target": "НПЗ"},     # дубль по составному
        {"city": "без даты"},                                                             # мусор
    ], open(INBOX, "w", encoding="utf-8"), ensure_ascii=False)

    rc = main()
    assert rc == 0
    a = json.load(open(ARCHIVE, encoding="utf-8"))
    assert len(a["strikes"]) == 3, a["strikes"]
    assert a["summary"]["total"] == 3, a["summary"]
    assert json.load(open(INBOX, encoding="utf-8")) == [], "inbox не очищен"
    assert json.load(open(RECENT, encoding="utf-8"))["count"] >= 1

    # повторный прогон того же inbox не плодит дубли
    json.dump([{"id": "new-1", "date": "2026-07-15", "city": "Чёрное море", "target": "танкеры"}],
              open(INBOX, "w", encoding="utf-8"), ensure_ascii=False)
    main()
    assert len(json.load(open(ARCHIVE, encoding="utf-8"))["strikes"]) == 3, "дубль просочился"

    # рассинхрон total чинится и без вливания
    a = json.load(open(ARCHIVE, encoding="utf-8"))
    a["summary"]["total"] = 42
    json.dump(a, open(ARCHIVE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump([], open(INBOX, "w", encoding="utf-8"))
    main()
    assert json.load(open(ARCHIVE, encoding="utf-8"))["summary"]["total"] == 3, "total не починен"

    # подозрительная коллизия id: тот же id old-1, но ДРУГОЕ событие (другое время).
    # Дефолт — отбросить (как настоящий дубль двух источников), но НЕ создать фантом:
    # архив не растёт, второго old-1 не появляется. (В stderr при этом идёт ⚠.)
    n0 = len(json.load(open(ARCHIVE, encoding="utf-8"))["strikes"])
    json.dump([{"id": "old-1", "date": "2026-07-01", "time": "ночь",
                "city": "Рязань", "target": "нефтебаза"}],
              open(INBOX, "w", encoding="utf-8"), ensure_ascii=False)
    main()
    a = json.load(open(ARCHIVE, encoding="utf-8"))
    assert len(a["strikes"]) == n0, "коллизия id не отброшена: %d" % len(a["strikes"])
    assert sum(1 for s in a["strikes"] if s.get("id") == "old-1") == 1, "фантом-дубль id"

    print("selfcheck OK: влито новое, 2 дубля и мусор отсечены, total пересчитан, "
          "inbox очищен, повтор не дублирует, дрейф total чинится без вливания, "
          "подозрительная коллизия id отброшена без фантома (с ⚠ в stderr)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
