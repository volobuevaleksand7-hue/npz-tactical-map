import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from radar_alerts import build_notifications, normalize_region, update_subscriber_alerts


RADAR = {
    "cities": {
        "Темрюк|Краснодарский край": {
            "name": "Темрюк", "region": "Краснодарский край", "bpla": True,
            "rocket": False, "pvo": False,
        },
        "Керчь|Республика Крым": {
            "name": "Керчь", "region": "Республика Крым", "bpla": False,
            "rocket": False, "pvo": False,
        },
    },
    "timestamp": 1783400000,
}


class RadarAlertsTest(unittest.TestCase):
    def test_normalize_region_accepts_aliases(self):
        self.assertEqual(normalize_region("Краснодар"), "Краснодарский край")
        self.assertEqual(normalize_region("all"), "all")

    def test_update_subscriber_alerts_sets_region_and_interval(self):
        info = {}
        update_subscriber_alerts(info, enabled=True, regions=["Краснодар"], interval_min=30)

        self.assertEqual(info["alerts"]["regions"], ["Краснодарский край"])
        self.assertEqual(info["alerts"]["interval_min"], 30)
        self.assertTrue(info["alerts"]["enabled"])

    def test_new_danger_sends_immediate_notification(self):
        subscribers = {
            "1": {"status": "active", "alerts": {"enabled": True, "regions": ["Краснодарский край"], "interval_min": 60}}
        }
        notices, state = build_notifications(subscribers, RADAR, {}, now_ts=1783400100)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["chat_id"], "1")
        self.assertIn("опасность БПЛА", notices[0]["text"])
        self.assertEqual(state["1"]["regions"]["Краснодарский край"]["active"], True)

    def test_active_threat_repeats_only_after_interval(self):
        subscribers = {
            "1": {"status": "active", "alerts": {"enabled": True, "regions": ["Краснодарский край"], "interval_min": 60}}
        }
        prev = {"1": {"regions": {"Краснодарский край": {"active": True, "last_sent_ts": 1783400000}}}}

        early, _ = build_notifications(subscribers, RADAR, prev, now_ts=1783401800)
        late, _ = build_notifications(subscribers, RADAR, prev, now_ts=1783403700)

        self.assertEqual(early, [])
        self.assertEqual(len(late), 1)
        self.assertIn("напоминание", late[0]["text"])

    def test_all_clear_is_sent_once(self):
        subscribers = {
            "1": {"status": "active", "alerts": {"enabled": True, "regions": ["Краснодарский край"], "interval_min": 30}}
        }
        prev = {"1": {"regions": {"Краснодарский край": {"active": True, "last_sent_ts": 1783400000}}}}
        clear_radar = {"cities": {"Темрюк|Краснодарский край": {"name": "Темрюк", "region": "Краснодарский край", "bpla": False}}}

        notices, state = build_notifications(subscribers, clear_radar, prev, now_ts=1783400300)
        second, _ = build_notifications(subscribers, clear_radar, state, now_ts=1783400600)

        self.assertEqual(len(notices), 1)
        self.assertIn("отбой", notices[0]["text"])
        self.assertEqual(second, [])

    def test_all_regions_subscriber_gets_matching_active_region(self):
        subscribers = {
            "1": {"status": "active", "alerts": {"enabled": True, "regions": ["all"], "interval_min": 0}}
        }

        notices, _ = build_notifications(subscribers, RADAR, {}, now_ts=1783400100)

        self.assertEqual(len(notices), 1)
        self.assertIn("Краснодарский край", notices[0]["text"])


if __name__ == "__main__":
    unittest.main()
