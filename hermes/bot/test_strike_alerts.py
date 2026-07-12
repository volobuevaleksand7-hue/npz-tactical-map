#!/usr/bin/env python3
"""Юнит-тест build_strike_notifications: дедуп, init-guard, фильтры attacks/регион."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strike_alerts import build_strike_notifications, format_strike, msk_time, strike_region

STRIKES = [
    {"id": "syzran-1", "date": "2026-07-12", "time": "13:34 UTC", "city": "Сызрань",
     "region": "Самарская область", "type": "drone", "target": "Сызранский НПЗ — установки"},
    {"id": "yaroslavl-1", "date": "2026-07-12", "time": "05:00 UTC", "city": "Ярославль",
     "region": "Ярославская область", "type": "rocket", "target": "НПЗ ЯНОС"},
]

SUBS = {
    "all_on":     {"status": "active", "alerts": {"enabled": True, "regions": ["all"], "attacks": True}},
    "samara_on":  {"status": "active", "alerts": {"enabled": True, "regions": ["Самарская обл."], "attacks": True}},
    "krasnodar":  {"status": "active", "alerts": {"enabled": True, "regions": ["Краснодарский край"], "attacks": True}},
    "attacks_off":{"status": "active", "alerts": {"enabled": True, "regions": ["all"], "attacks": False}},
    "paused":     {"status": "active", "alerts": {"enabled": False, "regions": ["all"], "attacks": True}},
    "inactive":   {"status": "inactive", "alerts": {"enabled": True, "regions": ["all"], "attacks": True}},
}


def test_region_and_flag_filters():
    notices, new_seen = build_strike_notifications(STRIKES, SUBS, seen=[])
    got = {(n["chat_id"], n["strike_id"]) for n in notices}
    # all_on получает оба удара
    assert ("all_on", "syzran-1") in got and ("all_on", "yaroslavl-1") in got
    # samara_on получает только Сызрань (его регион), не Ярославль
    assert ("samara_on", "syzran-1") in got
    assert ("samara_on", "yaroslavl-1") not in got
    # krasnodar не получает ничего (не его регионы)
    assert not any(c == "krasnodar" for c, _ in got)
    # attacks_off / paused / inactive — исключены
    for excluded in ("attacks_off", "paused", "inactive"):
        assert not any(c == excluded for c, _ in got), excluded
    assert new_seen == {"syzran-1", "yaroslavl-1"}
    print("ok: region + flag filters")


def test_dedup():
    # syzran-1 уже разослан → только yaroslavl-1 новый
    notices, new_seen = build_strike_notifications(STRIKES, SUBS, seen=["syzran-1"])
    ids = {n["strike_id"] for n in notices}
    assert ids == {"yaroslavl-1"}, ids
    assert new_seen == {"syzran-1", "yaroslavl-1"}
    print("ok: dedup")


def test_new_seen_grows_even_without_recipients():
    # Никто не подписан на регион — но id всё равно попадает в seen (не копится)
    only_krasnodar = {"k": {"status": "active",
                            "alerts": {"enabled": True, "regions": ["Краснодарский край"], "attacks": True}}}
    notices, new_seen = build_strike_notifications(STRIKES, only_krasnodar, seen=[])
    assert notices == []
    assert new_seen == {"syzran-1", "yaroslavl-1"}
    print("ok: new_seen grows without recipients")


def test_format_and_time():
    assert msk_time("13:34 UTC") == "16:34 МСК"
    assert msk_time("23:30 UTC") == "02:30 МСК"  # перелив за полночь
    txt = format_strike(STRIKES[0])
    assert "Сызрань" in txt and "Сызранский НПЗ" in txt and "16:34 МСК" in txt
    assert "удар БПЛА" in txt
    assert "ракетный удар" in format_strike(STRIKES[1])
    print("ok: format + time")


def test_region_norm():
    assert strike_region(STRIKES[0]) == "Самарская обл."
    assert strike_region(STRIKES[1]) == "Ярославская обл."
    print("ok: region normalization")


if __name__ == "__main__":
    test_region_and_flag_filters()
    test_dedup()
    test_new_seen_grows_even_without_recipients()
    test_format_and_time()
    test_region_norm()
    print("\nAll strike_alerts tests passed.")
