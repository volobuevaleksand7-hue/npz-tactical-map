"""
Self-check for H5 (radar-state.json schema unification + atomic write).

Loads update-radar-state.py and fetch-radar.py directly (hyphenated filenames,
so importlib.util.spec_from_file_location instead of a normal import).
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(HERE, filename))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


URS = _load("update_radar_state_t", "update-radar-state.py")
FR = _load("fetch_radar_t", "fetch-radar.py")


class AtomicSaveTest(unittest.TestCase):
    def test_save_round_trips_and_leaves_no_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "nested", "radar-state.json")
            state = {"schema_version": 2, "cities": [{"name": "x"}]}
            URS.save(state, out=out)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f), state)
            self.assertFalse(os.path.exists(out + ".tmp"))

    def test_save_never_corrupts_existing_file_on_serialize_failure(self):
        """Atomicity: if json.dump blows up mid-write, the file readers already see
        (data/radar-state.json) must stay exactly as it was — never truncated/partial."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "radar-state.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"old": True}, f)

            class Unserializable:
                pass

            with self.assertRaises(TypeError):
                URS.save({"bad": Unserializable()}, out=out)

            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"old": True})


class SchemaUnificationTest(unittest.TestCase):
    def test_fetch_radar_delegates_to_the_same_source_file(self):
        """H5 root-cause fix: fetch-radar.py no longer has its own convert_format()/
        non-atomic writer — it loads update-radar-state.py's fetch_json/normalize/save
        from the exact same file, so there is only one schema to keep in sync."""
        self.assertTrue(os.path.samefile(FR._canonical.__file__, URS.__file__))
        self.assertIs(FR._canonical.normalize, FR._canonical.normalize)  # sanity: attr exists
        self.assertTrue(callable(FR._canonical.save))

    def test_fetch_radar_main_writes_canonical_schema_atomically(self):
        payload = {
            "type": "state", "version": 3,
            "regions": {"r1": {"last_event_ts": 1000}},
            "cities": [{"name": "Темрюк", "region": "Краснодарский край", "bpla": True, "ts": 1000}],
            "districts": {}, "airport_markers": [], "feed": [],
        }
        calls = {"saved": None}

        def fake_fetch_json(url):
            return payload

        def fake_save(state, out=None):
            calls["saved"] = state

        orig_fetch, orig_save = FR._canonical.fetch_json, FR._canonical.save
        orig_argv = sys.argv
        FR._canonical.fetch_json = fake_fetch_json
        FR._canonical.save = fake_save
        sys.argv = ["fetch-radar.py"]
        try:
            FR.main()
        finally:
            FR._canonical.fetch_json, FR._canonical.save = orig_fetch, orig_save
            sys.argv = orig_argv

        self.assertIsNotNone(calls["saved"])
        # Same schema as update-radar-state.py: list-of-dicts cities, schema_version 2.
        self.assertEqual(calls["saved"]["schema_version"], 2)
        self.assertIsInstance(calls["saved"]["cities"], list)
        self.assertEqual(calls["saved"]["cities"][0]["name"], "Темрюк")

    def test_fetch_radar_dry_run_does_not_save(self):
        payload = {
            "cities": [{"name": "x", "region": "y", "ts": 1000}],
            "regions": {}, "districts": {}, "airport_markers": [], "feed": [],
        }
        calls = {"saved": False}

        orig_fetch, orig_save = FR._canonical.fetch_json, FR._canonical.save
        orig_argv = sys.argv
        FR._canonical.fetch_json = lambda url: payload
        FR._canonical.save = lambda state, out=None: calls.__setitem__("saved", True)
        sys.argv = ["fetch-radar.py", "--dry-run"]
        try:
            FR.main()
        finally:
            FR._canonical.fetch_json, FR._canonical.save = orig_fetch, orig_save
            sys.argv = orig_argv

        self.assertFalse(calls["saved"])


if __name__ == "__main__":
    unittest.main()
