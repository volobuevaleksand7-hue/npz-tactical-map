"""Тесты конвейера событий /lab/world. Без сети: python3 -m unittest tests.world.test_pipeline"""
import copy
import datetime as dt
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W = os.path.join(ROOT, "agents", "world")
sys.path.insert(0, W)
import _common as C  # noqa: E402


def load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(W, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V = load("validate_events", "validate-events.py")
A = load("approve", "approve.py")
N = load("notify", "notify.py")
WA = load("watch", "watch.py")

TODAY = dt.date(2026, 10, 11)


def cand(**kw):
    c = {"id": "2026-10-10-test", "occurred_at": "2026-10-10", "type": "outage",
         "region": "middle_east", "status": "reported",
         "title": "Остановлена работа терминала в порту", "summary": "Погрузка приостановлена.",
         "fuel_effect": "Экспорт сокращён.", "lat": 25.0, "lon": 55.0, "precision": "point",
         "radius_km": 0, "photo": None,
         "sources": [{"publisher": "Reuters", "url": "https://www.reuters.com/a", "date": "2026-10-10"}],
         "found_at": "2026-10-11T00:00:00Z", "agent": "world-events"}
    c.update(kw)
    return c


def run_validate(cands, existing=()):
    return V.validate(cands, list(existing), None, TODAY)


class TestValidator(unittest.TestCase):
    def test_ok_ready(self):
        self.assertEqual(run_validate([cand()])[0]["verdict"], "ready")

    def test_schema_errors(self):
        for kw in ({"type": "bogus"}, {"region": "mars"}, {"lat": 120}, {"occurred_at": "2026-10-20"},
                   {"occurred_at": "2026-09-01"}, {"sources": []}, {"status": "rumored"}):
            c = run_validate([cand(**kw)])[0]
            self.assertEqual(c["verdict"], "rejected", kw)
            self.assertTrue(c["checks"]["schema"].startswith("fail"), kw)

    def test_lexicon(self):
        for t in ("Слава Україні", "Удар по порту, терорист", "Горить склад ґаз"):
            c = run_validate([cand(title=t)])[0]
            self.assertEqual(c["verdict"], "rejected", t)
            self.assertTrue(c["checks"]["neutral_lexicon"].startswith("fail"))

    def test_dedup(self):
        old = cand(id="old", title="Остановлена работа терминала в порту")
        c = run_validate([cand(id="new")], [old])[0]
        self.assertEqual(c["verdict"], "rejected")
        self.assertIn("duplicate", c["reject_reason"])

    def test_two_publishers_rule(self):
        one = cand(type="strike", status="confirmed")
        c = run_validate([one])[0]
        self.assertEqual(c["status"], "reported")
        self.assertEqual(c["verdict"], "needs_source")
        reprint = cand(type="strike", status="confirmed", sources=[
            {"publisher": "Reuters", "url": "https://www.reuters.com/a"},
            {"publisher": "Reuters (через Al-Monitor)", "url": "https://www.al-monitor.com/b"}])
        self.assertEqual(run_validate([reprint])[0]["status"], "reported")
        two = cand(type="strike", status="confirmed", sources=[
            {"publisher": "Reuters", "url": "https://www.reuters.com/a"},
            {"publisher": "Argus Media", "url": "https://www.argusmedia.com/b"}])
        c = run_validate([two])[0]
        self.assertEqual((c["status"], c["verdict"]), ("confirmed", "ready"))

    def test_dead_url_rejects_and_unknown_does_not(self):
        c = cand()
        V.validate([c], [], {"https://www.reuters.com/a": False}, TODAY)
        self.assertEqual(c["verdict"], "rejected")
        c = cand()
        V.validate([c], [], {"https://www.reuters.com/a": None}, TODAY)
        self.assertEqual((c["verdict"], c["checks"]["urls_alive"]), ("ready", "unknown"))

    def test_atomic_write_valid_json(self):
        p = os.path.join(tempfile.mkdtemp(), "x.json")
        C.write_json_atomic(p, {"a": "ё"})
        self.assertEqual(json.load(open(p, encoding="utf-8")), {"a": "ё"})
        with self.assertRaises(TypeError):
            C.write_json_atomic(p, {"a": object()})
        self.assertEqual(json.load(open(p, encoding="utf-8")), {"a": "ё"})


class TestApprove(unittest.TestCase):
    def test_only_ready(self):
        r, nr = cand(id="r", verdict="ready"), cand(id="n", verdict="needs_source")
        q, e, log = A.apply({"candidates": [r, nr]}, {"events": [{"id": "z", "occurred_at": "2026-01-01"}]},
                            ["r", "n"])
        self.assertEqual([x["id"] for x in e["events"]], ["r", "z"])
        self.assertEqual(e["events"][0]["review"], "approved")
        self.assertNotIn("verdict", e["events"][0])
        self.assertEqual([x["id"] for x in q["candidates"]], ["n"])
        self.assertTrue(any("отказ" in l for l in log))

    def test_force_and_reject(self):
        n = cand(id="n", verdict="needs_source")
        q, e, _ = A.apply({"candidates": [n, cand(id="x", verdict="ready")]}, {"events": []}, ["n"], ["x"], True)
        self.assertEqual(len(e["events"]), 1)
        self.assertEqual(q["candidates"][0]["verdict"], "rejected")


class TestNotify(unittest.TestCase):
    def test_batch_and_mark(self):
        q = {"candidates": [cand(id=f"c{i}", verdict="ready") for i in range(10)]}
        sent = []
        n, text = N.run(q, lambda t: sent.append(t) or True)
        self.assertEqual((n, len(sent)), (8, 1))
        self.assertIn("approve c0", text)
        n2, _ = N.run(q, lambda t: True)
        self.assertEqual(n2, 2)
        self.assertEqual(N.run(q, lambda t: True)[0], 0)

    def test_failed_send_keeps_pending(self):
        q = {"candidates": [cand(verdict="ready")]}
        self.assertEqual(N.run(q, lambda t: False)[0], 0)
        self.assertNotIn("notified_at", q["candidates"][0])


class TestWatch(unittest.TestCase):
    NOW = dt.datetime(2026, 10, 11, 12, 0, tzinfo=dt.timezone.utc)

    def data(self):
        d = tempfile.mkdtemp()
        series = {"series": {
            "brent_spot": {"freq": "daily", "as_of": "2026-10-10", "value": 90, "stale": False, "error": None},
            "old": {"freq": "daily", "as_of": "2026-10-01", "value": 1, "stale": False, "error": None}}}
        index = {"generated_at": "2026-10-11T10:00:00Z", "world": {"coverage": 0.8}}
        for n, o in (("series", series), ("index", index), ("events-queue", {"candidates": []})):
            C.write_json_atomic(os.path.join(d, n + ".json"), o)
        return d

    def test_stale_series(self):
        d = self.data()
        r = WA.run(d, os.path.join(d, ".s.json"), now=self.NOW)
        self.assertFalse(r["ok"])
        self.assertTrue(any("old" in p for p in r["problems"]))
        self.assertFalse(any("brent_spot" in p for p in r["problems"]))

    def test_antiflap(self):
        d = self.data()
        sent = []
        st = os.path.join(d, ".s.json")
        r1 = WA.run(d, st, notify=True, send=lambda t: sent.append(t) or True, now=self.NOW)
        r2 = WA.run(d, st, notify=True, send=lambda t: sent.append(t) or True, now=self.NOW + dt.timedelta(hours=2))
        r3 = WA.run(d, st, notify=True, send=lambda t: sent.append(t) or True, now=self.NOW + dt.timedelta(hours=7))
        self.assertEqual((r1["notified"], r2["notified"], r3["notified"]), (True, False, True))
        self.assertEqual(len(sent), 2)

    def test_index_old_and_coverage(self):
        d = self.data()
        C.write_json_atomic(os.path.join(d, "index.json"),
                            {"generated_at": "2026-10-10T00:00:00Z", "world": {"coverage": 0.3}})
        r = WA.run(d, os.path.join(d, ".s.json"), now=self.NOW)
        self.assertTrue(any("index.json старше" in p for p in r["problems"]))
        self.assertTrue(any("coverage" in p for p in r["problems"]))

    def test_stale_queue_reminder_once_a_day(self):
        d = self.data()
        C.write_json_atomic(os.path.join(d, "events-queue.json"), {"candidates": [
            cand(id="q1", verdict="ready", found_at="2026-10-08T00:00:00Z")]})
        st = os.path.join(d, ".s.json")
        r = WA.run(d, st, notify=True, send=lambda t: True, now=self.NOW)
        self.assertTrue(any("q1" in p for p in r["problems"]))
        r = WA.run(d, st, now=self.NOW + dt.timedelta(hours=3))
        self.assertFalse(any("q1" in p for p in r["problems"]))


if __name__ == "__main__":
    unittest.main()
