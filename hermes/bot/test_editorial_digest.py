import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from editorial_digest import build_editorial_post, mark_published


class EditorialDigestTest(unittest.TestCase):
    def write_json(self, root, name, payload):
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def make_data_dir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = tmp.name
        self.write_json(root, "strikes.json", {"strikes": []})
        self.write_json(root, "fuel-voices.json", {"voices": []})
        self.write_json(root, "fuel-availability.json", {"exchange": {}, "regions": []})
        self.write_json(root, "fuel-state.json", {"national_balance": {}, "refineries": []})
        self.write_json(root, "grid-state.json", {"blackout_regions": [], "substations": []})
        return tmp

    def test_event_post_picks_fresh_npz_strike_and_highlights_main_point(self):
        tmp = self.make_data_dir()
        self.write_json(tmp.name, "strikes.json", {"strikes": [
            {
                "date": "2026-07-07",
                "city": "Ярославль",
                "region": "Ярославская обл.",
                "target": "НПЗ Славнефть-ЯНОС",
                "title": "Удар по ЯНОС",
                "detail": "После атаки фиксировали пожар в районе установки.",
                "confidence": "confirmed",
            }
        ]})
        self.write_json(tmp.name, "fuel-state.json", {
            "national_balance": {"capacity_offline_pct": 38},
            "refineries": [{"status": "down"}, {"status": "partial"}],
        })

        post = build_editorial_post(tmp.name, now="2026-07-07T12:00:00Z")

        self.assertEqual(post["kind"], "event")
        self.assertIn("<b>Ярославль:", post["text"])
        self.assertIn("Главное:", post["text"])
        self.assertIn("Почему важно:", post["text"])
        self.assertEqual(post["visual"]["type"], "event_card")
        self.assertEqual(post["card_payload"]["headline"], "Ярославль: НПЗ")

    def test_monitoring_post_uses_stats_when_no_event(self):
        tmp = self.make_data_dir()
        self.write_json(tmp.name, "fuel-availability.json", {
            "exchange": {"ai95_spb_rub_t": 74250, "trend": "stable"},
            "regions": [
                {"region": "Крым", "level": "critical"},
                {"region": "Севастополь", "level": "severe"},
                {"region": "Москва", "level": "calm"},
            ],
        })

        post = build_editorial_post(tmp.name, now="2026-07-07T12:00:00Z")

        self.assertEqual(post["kind"], "monitoring")
        self.assertIn("Топливный фронт: мониторинг", post["text"])
        self.assertIn("дефицит", post["text"])
        self.assertEqual(post["visual"]["type"], "monitoring_card")

    def test_english_voice_is_not_used_in_post(self):
        tmp = self.make_data_dir()
        self.write_json(tmp.name, "fuel-voices.json", {"voices": [
            {"city": "Moscow", "quote": "Gas stations are empty today", "date": "2026-07-07"},
            {"city": "Крым", "quote": "На заправке снова лимит двадцать литров.", "date": "2026-07-07"},
        ]})

        post = build_editorial_post(tmp.name, now="2026-07-07T12:00:00Z")

        self.assertNotIn("Gas stations", post["text"])
        self.assertIn("Крым", post["text"])

    def test_exact_fact_duplicate_is_blocked(self):
        tmp = self.make_data_dir()
        self.write_json(tmp.name, "strikes.json", {"strikes": [
            {"date": "2026-07-07", "city": "Ярославль", "target": "НПЗ", "title": "Удар по НПЗ"}
        ]})
        state_path = os.path.join(tmp.name, "editorial-state.json")
        first = build_editorial_post(tmp.name, state_path=state_path, now="2026-07-07T12:00:00Z")
        mark_published(first, state_path=state_path, now="2026-07-07T12:00:00Z")

        second = build_editorial_post(tmp.name, state_path=state_path, now="2026-07-07T13:00:00Z")

        self.assertFalse(second["should_publish"])
        self.assertEqual(second["reason"], "duplicate")


if __name__ == "__main__":
    unittest.main()
