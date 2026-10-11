#!/usr/bin/env python3
"""Решение владельца по кандидатам очереди /lab/world.

  approve.py <id> [<id>...] [--reject <id>...] [--force] [--queue P] [--events P]

approve: переносит ready-кандидата в events.json (review:"approved", approved_at),
удаляет из очереди. verdict != ready — отказ без --force. reject: помечает в очереди
verdict:"rejected", decided_at. events.json сортируется по occurred_at убыв.
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C  # noqa: E402

SERVICE = {"checks", "verdict", "reject_reason", "found_at", "agent", "notified_at", "decided_at"}


def apply(queue, events, approve_ids, reject_ids=(), force=False, now=None):
    """-> (queue, events, log[str]); чистая функция."""
    now = now or C.now_iso()
    cands = queue.get("candidates", [])
    evs = events.get("events", [])
    log = []
    for cid in approve_ids:
        c = next((x for x in cands if x.get("id") == cid), None)
        if c is None:
            log.append(f"{cid}: нет в очереди")
            continue
        if c.get("verdict") != "ready" and not force:
            log.append(f"{cid}: отказ, verdict={c.get('verdict')} (нужен --force)")
            continue
        if any(e.get("id") == cid for e in evs):
            log.append(f"{cid}: уже в events.json")
            continue
        ev = {k: v for k, v in c.items() if k not in SERVICE}
        ev["review"], ev["approved_at"] = "approved", now
        ev.setdefault("index_effect", None)
        evs.append(ev)
        cands.remove(c)
        log.append(f"{cid}: одобрен")
    for cid in reject_ids:
        c = next((x for x in cands if x.get("id") == cid), None)
        if c is None:
            log.append(f"{cid}: нет в очереди")
            continue
        c["verdict"], c["reject_reason"] = "rejected", "отклонено владельцем"
        c["decided_at"] = now
        log.append(f"{cid}: отклонён")
    evs.sort(key=lambda e: str(e.get("occurred_at", "")), reverse=True)
    events["events"] = evs
    events["generated_at"] = now
    queue["candidates"] = cands
    return queue, events, log


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--reject", nargs="+", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--queue", default=C.QUEUE)
    ap.add_argument("--events", default=C.EVENTS)
    a = ap.parse_args(argv)
    if not a.ids and not a.reject:
        ap.error("укажи id")
    q = C.load_json(a.queue, {"candidates": []})
    e = C.load_json(a.events, {"events": []})
    q, e, log = apply(q, e, a.ids, a.reject, a.force)
    print("\n".join(log))
    C.write_json_atomic(a.events, e)
    C.write_json_atomic(a.queue, q)
    return 0 if not any("отказ" in l or "нет в очереди" in l for l in log) else 1


if __name__ == "__main__":
    sys.exit(main())
