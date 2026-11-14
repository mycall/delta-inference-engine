"""Check shared response headers on real HTTP routes, without a model or GPU."""
from pathlib import Path
import unittest
import urllib.error
import urllib.request

from serve.frontend import ChatTemplate
from serve.server import ByteTokenizer, MockEngine, Service, serve


class SecurityHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tok = ByteTokenizer()
        engine = MockEngine(tok, "ok", max_context=4096)
        cls.svc = Service(engine, tok, ChatTemplate(Path(__file__).parent / "chat_template.jinja"))
        cls.httpd = serve(cls.svc, port=0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_html_api_asset_and_error_responses(self):
        for path, status in [("/", 200), ("/health", 200), ("/web/app.js", 200), ("/not-a-route", 404)]:
            with self.subTest(path=path):
                try:
                    response = self.opener.open(self.base + path, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    self.assertEqual(response.status, status)
                    self.assertIn("nosniff", response.headers.get_all("X-Content-Type-Options", []))
                    self.assertEqual(response.headers["Server"], "Strata")
                    response.read()


if __name__ == "__main__":
    unittest.main()
