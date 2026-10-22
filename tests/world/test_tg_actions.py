import importlib.util, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "..", "..", "agents", "world")
sys.path.insert(0, W)


def load(name, f):
    spec = importlib.util.spec_from_file_location(name, os.path.join(W, f))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


T = load("tg_actions", "tg_actions.py")
N = load("notify", "notify.py")


class TestTg(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.q = os.path.join(self.d, "q.json")
        self.e = os.path.join(self.d, "e.json")
        c = {"id": "2026-10-21-x", "verdict": "ready", "occurred_at": "2026-10-21", "region": "europe",
             "status": "reported", "title": "t", "sources": []}
        json.dump({"candidates": [c]}, open(self.q, "w"))
        json.dump({"events": []}, open(self.e, "w"))
        self.h = T.short_id("2026-10-21-x")
        self.run = lambda args: (__import__("subprocess").run(args, capture_output=True, text=True).returncode,
                                 __import__("subprocess").run(args, capture_output=True, text=True).stdout)

    def test_markup_len(self):
        m = N.build_markup([{"id": "2026-10-21-x"}])
        for b in m["inline_keyboard"][0]:
            self.assertLessEqual(len(b["callback_data"].encode()), 64)

    def test_not_owner(self):
        self.assertEqual(T.handle(f"wev:a:{self.h}", 1, self.q, self.e)[0], "Нет доступа")

    def test_approve(self):
        toast, line, ok = T.handle(f"wev:a:{self.h}", 609952529, self.q, self.e, runner=self.run)
        self.assertTrue(ok)
        self.assertEqual(json.load(open(self.e))["events"][0]["review"], "approved")

    def test_reject_and_repeat(self):
        toast, line, ok = T.handle(f"wev:r:{self.h}", 609952529, self.q, self.e, runner=self.run)
        self.assertFalse(ok)
        self.assertEqual(json.load(open(self.q))["candidates"][0]["verdict"], "rejected")
        self.assertEqual(json.load(open(self.e))["events"], [])


if __name__ == "__main__":
    unittest.main()
