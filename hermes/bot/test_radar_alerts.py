import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import radar_alerts
from radar_alerts import build_notifications, normalize_region, split_message, update_subscriber_alerts


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

    # ── H11: 4096-char preflight/split ──────────────────────────────────

    def test_split_message_noop_under_limit(self):
        text = "short message"
        self.assertEqual(split_message(text), [text])

    def test_split_message_splits_on_line_boundaries_under_limit(self):
        # 50 lines of 100 chars (+newline) = ~5050 chars > 4096, must split into >=2 chunks,
        # each individually under the limit, with every original line preserved somewhere.
        lines = ["region-%02d " % i + "x" * 90 for i in range(50)]
        text = "\n".join(lines)
        chunks = split_message(text, limit=4096)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 4096)
        rejoined_lines = "\n".join(chunks).split("\n")
        self.assertEqual(rejoined_lines, lines)

    def test_split_message_hard_slices_a_single_oversized_line(self):
        text = "x" * 9000  # one line, no newlines, 2x the limit
        chunks = split_message(text, limit=4096)
        self.assertEqual(len(chunks), 3)
        for c in chunks:
            self.assertLessEqual(len(c), 4096)
        self.assertEqual("".join(chunks), text)

    # ── H10: try/except on send, no batch-wide resend on one failure ────

    def test_send_text_catches_exceptions_instead_of_raising(self):
        def boom(token, chat_id, text):
            raise RuntimeError("429 Too Many Requests")

        orig = radar_alerts.send_message
        radar_alerts.send_message = boom
        try:
            ok, err = radar_alerts.send_text("tok", "1", "hello")
        finally:
            radar_alerts.send_message = orig
        self.assertFalse(ok)
        self.assertIsInstance(err, RuntimeError)

    def test_send_text_splits_and_sends_every_chunk(self):
        calls = []

        def fake_send(token, chat_id, text):
            calls.append(text)
            return {"ok": True}

        orig = radar_alerts.send_message
        radar_alerts.send_message = fake_send
        try:
            long_text = "\n".join("line %d " % i + "x" * 90 for i in range(50))
            ok, err = radar_alerts.send_text("tok", "1", long_text)
        finally:
            radar_alerts.send_message = orig
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertGreater(len(calls), 1)

    def test_main_send_persists_incrementally_on_partial_failure(self):
        """H10 integration check: chat '1' fails to send, chat '2' succeeds. The state file
        must end up reflecting ONLY chat '2' as delivered — chat '1' stays as if nothing
        happened, so the next run naturally retries just that one notice instead of the
        whole batch (which is what used to happen when jsave() only ran once, after the loop,
        and a mid-loop exception skipped it for everyone)."""
        with tempfile.TemporaryDirectory() as tmp:
            bot_dir = os.path.join(tmp, "bot")
            os.makedirs(bot_dir)
            with open(os.path.join(bot_dir, "token"), "w") as f:
                f.write("fake-token")
            subs_path = os.path.join(bot_dir, "subscribers.json")
            state_path = os.path.join(bot_dir, "radar-alert-state.json")
            data_dir = os.path.join(tmp, "data")
            os.makedirs(data_dir)

            subs = {
                "subscribers": {
                    "1": {"status": "active", "alerts": {"enabled": True, "regions": ["Краснодарский край"], "interval_min": 0}},
                    "2": {"status": "active", "alerts": {"enabled": True, "regions": ["Республика Крым"], "interval_min": 0}},
                }
            }
            with open(subs_path, "w", encoding="utf-8") as f:
                json.dump(subs, f)
            radar = {
                "cities": {
                    "a": {"name": "Темрюк", "region": "Краснодарский край", "bpla": True},
                    "b": {"name": "Керчь", "region": "Республика Крым", "bpla": True},
                }
            }
            with open(os.path.join(data_dir, "radar-state.json"), "w", encoding="utf-8") as f:
                json.dump(radar, f)

            def flaky_send(token, chat_id, text):
                if chat_id == "1":
                    raise RuntimeError("429 Too Many Requests")
                return {"ok": True}

            orig_send = radar_alerts.send_message
            orig_bot_dir, orig_subs, orig_state, orig_data = (
                radar_alerts.BOT_DIR, radar_alerts.SUBS_PATH, radar_alerts.STATE_PATH, radar_alerts.DATA)
            orig_argv = sys.argv
            radar_alerts.send_message = flaky_send
            radar_alerts.BOT_DIR = bot_dir
            radar_alerts.SUBS_PATH = subs_path
            radar_alerts.STATE_PATH = state_path
            radar_alerts.DATA = data_dir
            sys.argv = ["radar_alerts.py", "--send"]
            try:
                radar_alerts.main()  # must not raise despite chat "1" failing
            finally:
                radar_alerts.send_message = orig_send
                radar_alerts.BOT_DIR, radar_alerts.SUBS_PATH, radar_alerts.STATE_PATH, radar_alerts.DATA = (
                    orig_bot_dir, orig_subs, orig_state, orig_data)
                sys.argv = orig_argv

            with open(state_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertNotIn("1", saved)
            self.assertIn("2", saved)
            self.assertTrue(saved["2"]["regions"]["Республика Крым"]["active"])

    def test_send_text_reports_failure_if_any_chunk_fails(self):
        state = {"n": 0}

        def flaky_send(token, chat_id, text):
            state["n"] += 1
            if state["n"] == 2:
                raise RuntimeError("400 message too long")
            return {"ok": True}

        orig = radar_alerts.send_message
        radar_alerts.send_message = flaky_send
        try:
            long_text = "\n".join("line %d " % i + "x" * 90 for i in range(50))
            ok, err = radar_alerts.send_text("tok", "1", long_text)
        finally:
            radar_alerts.send_message = orig
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
