import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from channel_cleanup_audit import audit_posts, parse_tme_posts


SAMPLE_HTML = """
<div class="tgme_widget_message" data-post="NPZmap/31">
  <a class="tgme_widget_message_date" href="https://t.me/NPZmap/31"><time datetime="2026-07-07T04:00:00+00:00"></time></a>
  <div class="tgme_widget_message_text">Fuel front update: refinery pressure is rising</div>
</div>
<div class="tgme_widget_message" data-post="NPZmap/32">
  <a class="tgme_widget_message_date" href="https://t.me/NPZmap/32"><time datetime="2026-07-07T04:20:00+00:00"></time></a>
  <div class="tgme_widget_message_text">Топливный фронт РФ — сводка за 7 июля</div>
</div>
<div class="tgme_widget_message" data-post="NPZmap/33">
  <a class="tgme_widget_message_date" href="https://t.me/NPZmap/33"><time datetime="2026-07-07T04:40:00+00:00"></time></a>
  <div class="tgme_widget_message_text">Топливный фронт РФ — сводка за 7 июля</div>
</div>
<div class="tgme_widget_message" data-post="NPZmap/34">
  <a class="tgme_widget_message_date" href="https://t.me/NPZmap/34"><time datetime="2026-07-07T05:00:00+00:00"></time></a>
  <div class="tgme_widget_message_text"><b>Омск: НПЗ</b><br/>Главное: Омский НПЗ. Почему важно: дефицит.</div>
</div>
"""


class ChannelCleanupAuditTest(unittest.TestCase):
    def test_parse_tme_posts_extracts_ids_dates_and_text(self):
        posts = parse_tme_posts(SAMPLE_HTML)

        self.assertEqual([p["message_id"] for p in posts], [31, 32, 33, 34])
        self.assertEqual(posts[0]["url"], "https://t.me/NPZmap/31")
        self.assertIn("Fuel front", posts[0]["text"])

    def test_audit_posts_marks_english_duplicate_and_keeps_editorial_post(self):
        candidates = audit_posts(parse_tme_posts(SAMPLE_HTML))
        by_id = {c["message_id"]: c for c in candidates}

        self.assertIn("english_or_mixed", by_id[31]["reasons"])
        self.assertIn("weak_no_main_point", by_id[32]["reasons"])
        self.assertIn("duplicate_text", by_id[33]["reasons"])
        self.assertNotIn(34, by_id)


if __name__ == "__main__":
    unittest.main()
