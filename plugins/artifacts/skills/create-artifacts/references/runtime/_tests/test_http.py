import importlib.util
import json
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("artifact_server",ROOT/"scripts"/"app.py")
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
from _tests.test_app import fixture_root

class HttpSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        root=fixture_root(cls.temp.name)
        report=root/'reports/audit.html'
        report.write_text('<main>'+report.read_text()+'</main>')
        app.STORE=app.CatalogStore(root)
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
    def get(self,path): return urllib.request.urlopen(self.base+path,timeout=3)
    def test_health_readiness_and_status_are_distinct(self):
        self.assertEqual(json.load(self.get("/healthz"))["status"],"healthy")
        self.assertEqual(json.load(self.get("/readyz"))["status"],"ready")
        self.assertIn(json.load(self.get("/api/status"))["status"],{"clean","warning","error"})
    def test_internal_and_traversal_paths_are_denied(self):
        for path in ("/.git/config","/_app/catalog.py","/_tests/test_app.py","/raw/../CLAUDE.md"):
            with self.assertRaises(urllib.error.HTTPError) as caught: self.get(path)
            self.assertEqual(caught.exception.code,404)
    def test_artifact_is_enriched_with_context(self):
        body=self.get("/reports/audit.html").read().decode()
        self.assertIn("Relevant docs &amp; references",body)
        self.assertIn("Related artifacts",body)
    def test_security_headers_and_asset(self):
        response=self.get("/assets/favicon.svg")
        self.assertIn("default-src",response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"],"nosniff")
        self.assertIn("image/svg+xml",response.headers["Content-Type"])
        response.close()

if __name__=="__main__":unittest.main()
