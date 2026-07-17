#!/usr/bin/env python3
"""Assert-тесты для agents/gen-wave.py — схлопывание архива и «идёт сейчас».

Ловят регрессию бага 17.07: на проде висели 4 волны с бейджем «ИДЁТ СЕЙЧАС»
и растущей длительностью (до 97 ч), потому что архив append-only содержит
start-строку (ended_at=null) и end-строку с одним id, а рендер считал живой
любую строку без ended_at.

Запуск: python3 agents/test_gen_wave.py
"""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "gen_wave",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "gen-wave.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
dedupe_events = _mod.dedupe_events
is_live_event = _mod.is_live_event
render_archive_cards = _mod.render_archive_cards


def _pair(ev_id, started, ended, peak_c_start, peak_c_end):
    """Реальная форма архива: детектор пишет строку и на start, и на end."""
    return [
        {"id": ev_id, "date": started[:10], "started_at": started, "ended_at": None,
         "peak_cities": peak_c_start, "peak_regions": 9, "region_list": ["А", "Б"]},
        {"id": ev_id, "date": started[:10], "started_at": started, "ended_at": ended,
         "peak_cities": peak_c_end, "peak_regions": 10, "region_list": ["А", "Б", "В"]},
    ]


def test_dedupe_collapses_pair():
    """start+end с одним id → одна запись, побеждает завершённая (полные пики)."""
    evs = _pair("2026-07-15-2320", "2026-07-15T23:20:09Z", "2026-07-16T00:00:08Z", 25, 27)
    out = dedupe_events(evs)
    assert len(out) == 1, "ожидалась 1 запись, got %d" % len(out)
    assert out[0]["ended_at"] is not None, "победить должна завершённая запись"
    assert out[0]["peak_cities"] == 27, "пик должен браться из end-записи"
    print("  PASS: test_dedupe_collapses_pair")


def test_dedupe_keeps_orphan_start():
    """Осиротевшая start-строка (end не записан) не теряется."""
    evs = [{"id": "2026-07-17-0100", "started_at": "2026-07-17T01:00:00Z",
            "ended_at": None, "peak_cities": 30, "peak_regions": 8, "region_list": []}]
    out = dedupe_events(evs)
    assert len(out) == 1 and out[0]["ended_at"] is None
    print("  PASS: test_dedupe_keeps_orphan_start")


def test_dedupe_sorted_desc():
    """Лента — новые сверху."""
    evs = _pair("2026-07-12-2237", "2026-07-12T22:37:00Z", "2026-07-13T01:29:00Z", 31, 31) \
        + _pair("2026-07-15-2320", "2026-07-15T23:20:09Z", "2026-07-16T00:00:08Z", 25, 27)
    out = dedupe_events(evs)
    assert [e["id"] for e in out] == ["2026-07-15-2320", "2026-07-12-2237"]
    print("  PASS: test_dedupe_sorted_desc")


def test_live_only_from_state():
    """🔴 Ядро бага: пустой ended_at ≠ «идёт сейчас». Живая — только та, что
    совпала с current_event_id при active=True."""
    orphan = {"id": "2026-07-12-2237", "started_at": "2026-07-12T22:37:00Z", "ended_at": None}
    assert is_live_event(orphan, {"active": False, "current_event_id": None}) is False, \
        "волна без ended_at при active=False НЕ живая (это и был баг: 97 ч «идёт сейчас»)"
    assert is_live_event(orphan, {"active": True, "current_event_id": "другой-id"}) is False, \
        "активна ДРУГАЯ волна — эта не живая"
    assert is_live_event(orphan, {"active": True, "current_event_id": "2026-07-12-2237"}) is True, \
        "совпала с current_event_id при active=True → живая"
    print("  PASS: test_live_only_from_state")


def test_no_phantom_badge_when_quiet():
    """Интеграция: тихое состояние → ни одного бейджа и ни одной выдуманной длительности."""
    evs = _pair("2026-07-12-2237", "2026-07-12T22:37:00Z", "2026-07-13T01:29:00Z", 31, 31)
    html = render_archive_cards(evs, {"active": False, "current_event_id": None})
    assert "ИДЁТ СЕЙЧАС" not in html, "при active=False бейджа быть не должно"
    assert html.count('class="archive-card"') == 1, "пара должна схлопнуться в 1 карточку"
    print("  PASS: test_no_phantom_badge_when_quiet")


def test_orphan_has_no_invented_duration():
    """Осиротевшая волна: конец неизвестен → длительность НЕ выдумываем."""
    evs = [{"id": "2026-07-17-0100", "started_at": "2026-07-17T01:00:00Z",
            "ended_at": None, "peak_cities": 30, "peak_regions": 8, "region_list": ["А"]}]
    html = render_archive_cards(evs, {"active": False, "current_event_id": None})
    assert "длительность" not in html, "у осиротевшей волны длительности быть не должно"
    assert "ИДЁТ СЕЙЧАС" not in html
    print("  PASS: test_orphan_has_no_invented_duration")


if __name__ == "__main__":
    test_dedupe_collapses_pair()
    test_dedupe_keeps_orphan_start()
    test_dedupe_sorted_desc()
    test_live_only_from_state()
    test_no_phantom_badge_when_quiet()
    test_orphan_has_no_invented_duration()
    print("OK")
