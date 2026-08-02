#!/usr/bin/env python3
"""Сводка берёт обложку СВОЕГО дня, а чужую — только с громким предупреждением.

Ловит инцидент 02.08.2026: в утреннюю сводку уехала картинка с подписью «31.07.2026»,
потому что своей ещё не было, а выбор молча падал на ближайшую существующую.
Запуск: python3 test_cover_pick.py
"""
import io, os, sys, tempfile, contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NPZ_BOT_DIR", tempfile.mkdtemp())
os.environ["NPZ_REPO"] = tempfile.mkdtemp()

import broadcast as B
import day_state as DS

TODAY = DS.today_iso()
os.makedirs(os.path.join(B.REPO, "assets"), exist_ok=True)


def with_covers(dates, strike_dates, build_ok=False):
    """Кладёт обложки на диск, подменяет данные ударов и сборщик. Возвращает (путь, лог)."""
    for f in os.listdir(os.path.join(B.REPO, "assets")):
        os.remove(os.path.join(B.REPO, "assets", f))
    for d in dates:
        open(B.cover_path_for(d), "w").write("png")
    orig_load, orig_build = B.load, B.build_cover_for
    B.load = lambda fn, default=None: {"strikes": [{"date": d} for d in strike_dates]}
    B.build_cover_for = lambda d: (open(B.cover_path_for(d), "w").write("png") or True) if build_ok else False
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return B.latest_cover_path(), buf.getvalue()
    finally:
        B.load, B.build_cover_for = orig_load, orig_build


# сегодняшняя обложка есть — берём её и молчим
path, log = with_covers([TODAY, "2026-07-31"], [TODAY, "2026-07-31"])
assert path == B.cover_path_for(TODAY), path
assert "🔴" not in log, log

# своей нет, но сборщик её делает — берём свежесобранную, чужую не трогаем
path, log = with_covers(["2026-07-31"], [TODAY, "2026-07-31"], build_ok=True)
assert path == B.cover_path_for(TODAY), path
assert "🔴" not in log, log

# 🔴 своей нет и собрать не вышло — чужая допустима, но об этом обязан быть крик в лог
path, log = with_covers(["2026-07-31"], [TODAY, "2026-07-31"])
assert path == B.cover_path_for("2026-07-31"), path
assert "🔴" in log and "31" in log, log

# нет вообще ничего — None и предупреждение, а не тихий возврат
path, log = with_covers([], [TODAY])
assert path is None and "🔴" in log, (path, log)

print("test_cover_pick: ok")
