#!/usr/bin/env python3
"""Сводка одного дня и вида публикуется один раз.

Ловит ровно то, из-за чего в @NPZmap 29-31.07 каждая сводка выходила дважды: второй
публикатор заходил в do_briefing и тот отправлял заново. Запуск: python3 test_briefing_guard.py
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_BOT_DIR", tempfile.mkdtemp())

import broadcast as B
import day_state as DS


def run(state, **kw):
    """Зовёт do_briefing на подсунутом состоянии и говорит, дошло ли до сборки данных."""
    reached = []
    orig_load, orig_gather = DS.load_state, B._gather_briefing_data
    DS.load_state = lambda: state
    B._gather_briefing_data = lambda **k: reached.append(1) or (_ for _ in ()).throw(
        SystemExit("дошли до отправки"))
    try:
        B.do_briefing("evening", **kw)
    except SystemExit:
        pass
    finally:
        DS.load_state, B._gather_briefing_data = orig_load, orig_gather
    return bool(reached)


day = DS.today_iso()
key = DS.make_key(day, "briefing-evening", "", "")

fresh = DS.ensure_today(None, day)
assert run(fresh), "первая сводка дня должна публиковаться"

published = DS.mark_published(DS.ensure_today(None, day), key)
assert not run(published), "🔴 повторная сводка за тот же день прошла guard"

assert run(published, force=True), "--force должен пробивать guard"

# ключ разный для утра и вечера — утренняя не должна глушить вечернюю
assert DS.make_key(day, "briefing-morning", "", "") != key

print("test_briefing_guard: ok")
