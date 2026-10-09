import functools
import http.server
import threading
import unittest
from pathlib import Path

from seo_bot import audit, compliance, crawler

FIXTURE = Path(__file__).parent / "fixture_site"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class AuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=str(FIXTURE))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        cls.reports = {r.url.rsplit("/", 1)[-1] or "index": r
                       for r in audit.audit_site(crawler.crawl(cls.base, limit=10))}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def messages(self, page):
        return " ".join(i.message for i in self.reports[page].issues)

    def test_crawler_follows_internal_links(self):
        self.assertEqual(set(self.reports), {"index", "services.html"})

    def test_good_page_scores_higher(self):
        self.assertGreater(self.reports["index"].score, self.reports["services.html"].score)

    def test_detects_core_issues(self):
        m = self.messages("services.html")
        for expected in ("Missing meta description", "2 <h1>", "viewport", "Physiotherapy schema", "Thin content"):
            self.assertIn(expected, m)
        self.assertIn("1 of 1 images have no alt", self.messages("index"))

    def test_recognises_physiotherapy_schema(self):
        self.assertIn("Physiotherapy", self.reports["index"].schema_types)
        self.assertNotIn("Physiotherapy schema", self.messages("index"))

    def test_compliance_flags(self):
        rules = {f.rule for f in self.reports["services.html"].compliance}
        self.assertTrue({"testimonial", "guarantee", "cure", "superlative", "inducement"} <= rules)
        self.assertEqual(self.reports["index"].compliance, [])

    def test_compliance_ignores_neutral_copy(self):
        self.assertEqual(compliance.check("Evidence-based rehab to help you return to squatting."), [])

    def test_markdown_report(self):
        md = audit.to_markdown(list(self.reports.values()), self.base)
        self.assertIn("Advertising-compliance flags", md)


class PromptTest(unittest.TestCase):
    def test_system_prompt_fills_profile(self):
        from seo_bot.ai import system_prompt
        s = system_prompt({"name": "PhysioParth", "services": ["A", "B"]})
        self.assertIn("PhysioParth", s)
        self.assertIn("A, B", s)
        self.assertIn("[not set]", s)


if __name__ == "__main__":
    unittest.main()
