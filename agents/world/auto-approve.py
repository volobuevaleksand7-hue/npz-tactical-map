#!/usr/bin/env python3
"""Автоодобрение кандидатов /lab/world проверщиком (04.11.2026, владелец: «сделай проверщика, пусть проверяет и пускает в прод»).

  python3 agents/world/auto-approve.py [--dry] [--max 6] [--days 14]

Работает после validate-events.py (схема, живые URL, нейтральная лексика, два издателя для силовых событий).
Одобряет кандидата, только если выполнено ВСЁ:
  1. verdict == ready;
  2. тексты чистые: в русских полях нет букв с диакритикой и чужих письменностей («Пाकिस्तан», «stratégique»),
     нет слов из смеси кириллицы и латиницы; в английских — только латиница;
  3. доказательность: confirmed, либо ≥2 независимых издателя, либо тип из shortage/outage/opec/stocks_release/
     sanctions/other (хозяйственные новости, где достаточно одного издателя); силовые типы (strike, attack_shipping,
     seizure, naval) — только при ≥2 издателях;
  4. свежесть: occurred_at не старше --days суток;
  5. не больше --max одобрений за прогон.
Испорченные тексты помечаются verdict rejected (garbled_text). Остальные остаются в очереди как были.
Одобренные переносит approve.apply (review: approved), владельцу в Telegram уходит список — отклонить можно
`python3 agents/world/approve.py --reject <id>` (событие уже в events.json: тогда править review вручную)."""
import argparse
import datetime
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402
import approve as A  # noqa: E402

RU_FIELDS = ("title", "summary", "fuel_effect")
EN_FIELDS = ("title_en", "summary_en", "fuel_effect_en")
SECURITY = {"strike", "attack_shipping", "seizure", "naval"}


def _script(ch):
    n = unicodedata.name(ch, "")
    if n.startswith("CYRILLIC"):
        return "C"
    if n.startswith("LATIN"):
        return "L" if " WITH " not in n else "LX"   # LX — латиница с диакритикой
    return "?"


def garbled(c):
    """-> строка с причиной или None."""
    for f in RU_FIELDS:
        t = c.get(f) or ""
        if not isinstance(t, str):
            return f"{f}: не строка"
        for ch in t:
            if ch.isalpha() and _script(ch) in ("?", "LX"):
                return f"{f}: символ {ch!r} ({unicodedata.name(ch, '?')})"
        for w in re.findall(r"[^\W\d_]+", t):
            if any(_script(x) == "C" for x in w) and any(_script(x) == "L" for x in w):
                return f"{f}: смесь кириллицы и латиницы в слове {w!r}"
    for f in EN_FIELDS:
        t = c.get(f) or ""
        for ch in t if isinstance(t, str) else "":
            if ch.isalpha() and _script(ch) == "C":
                return f"{f}: кириллица в английском тексте"
            if ch.isalpha() and _script(ch) == "?":
                return f"{f}: символ {ch!r} ({unicodedata.name(ch, '?')})"
    return None


def evidence_ok(c):
    n = (c.get("checks") or {}).get("independent_sources") or 0
    if c.get("status") == "confirmed" or n >= 2:
        return True
    return c.get("type") not in SECURITY


def decide(c, days, today):
    """-> ("approve"|"reject"|"skip", причина)."""
    if c.get("verdict") != "ready":
        return "skip", f"verdict={c.get('verdict')}"
    g = garbled(c)
    if g:
        return "reject", g
    if not evidence_ok(c):
        return "skip", "силовое событие с одним издателем"
    try:
        age = (today - datetime.date.fromisoformat(str(c.get("occurred_at"))[:10])).days
    except ValueError:
        return "skip", "нет даты"
    if age > days:
        return "skip", f"старше {days} сут."
    return "approve", "ok"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--queue", default=C.QUEUE)
    ap.add_argument("--events", default=C.EVENTS)
    a = ap.parse_args(argv)
    q = C.load_json(a.queue, {"candidates": []})
    e = C.load_json(a.events, {"events": []})
    today = datetime.datetime.now(datetime.timezone.utc).date()
    approve_ids, rejected, log = [], [], []
    for c in q.get("candidates", []):
        act, why = decide(c, a.days, today)
        log.append(f"{act:8} {c.get('id')} — {why}")
        if act == "approve" and len(approve_ids) < a.max:
            approve_ids.append(c["id"])
        elif act == "reject":
            rejected.append((c, why))
    print("\n".join(log))
    if a.dry:
        print(f"[dry] одобрить {len(approve_ids)}, отклонить {len(rejected)}")
        return 0
    titles = {c["id"]: c.get("title", "") for c in q.get("candidates", [])}
    for c, why in rejected:
        c["verdict"], c["reject_reason"], c["decided_at"] = "rejected", "garbled_text: " + why, C.now_iso()
    q, e, alog = A.apply(q, e, approve_ids)
    print("\n".join(alog))
    if approve_ids or rejected:
        C.write_json_atomic(a.events, e)
        C.write_json_atomic(a.queue, q)
    ok = [i for i in approve_ids if any(x.get("id") == i for x in e.get("events", []))]
    if ok:
        try:
            import notify as N
            N.tg_send("✅ Проверщик /world одобрил %d событий:\n%s" % (len(ok), "\n".join("• " + titles[i] for i in ok)))
        except Exception as ex:  # noqa: BLE001
            print("notify: %s" % ex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
