import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CAPTURE = ROOT / "scripts/capture-cortex-evidence-stream.py"
WRAPPER = ROOT / "scripts/pr-report.py"


class StreamHandler(BaseHTTPRequestHandler):
    mode = "valid"
    seen_host = None

    def do_GET(self):
        type(self).seen_host = self.headers.get("Host")
        self.send_response(200)
        if self.mode == "html":
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>login</html>")
            return
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if self.mode == "empty":
            return
        high = 100 if self.mode == "sparse" else 7
        self.wfile.write(
            (f'event: snapshot\ndata: {{"highWatermark":{high},"historicalCount":1}}\n\n'
             'event: evidence\nid: opaque-7\ndata: {"event":{"id":7,"kind":"tool"}}\n\n').encode())

    def log_message(self, *_args):
        pass


class CortexEvidenceCaptureTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), StreamHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_capture(self, output, *extra, wrapper=False):
        command = ["python3", str(WRAPPER if wrapper else CAPTURE)]
        if wrapper:
            command.extend(["watch-evidence", "--"])
        command.extend(["--server", f"http://127.0.0.1:{self.server.server_port}",
                        "--branch", "fix/test", "--output", str(output), *extra])
        return subprocess.run(command, capture_output=True, text=True,
                              env={**os.environ, "CORTEX_API_TOKEN": "test-token"})

    def test_valid_stream_is_captured_atomically_with_host_override(self):
        with tempfile.TemporaryDirectory() as directory:
            StreamHandler.mode = "valid"
            output = Path(directory) / "bundle.jsonl"
            result = self.run_capture(output, "--host-header", "localhost:3100")
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([record["record_type"] for record in records],
                             ["bundle-header", "snapshot", "evidence", "bundle-footer"])
            self.assertEqual(records[-1]["evidence_events"], 1)
            self.assertEqual(StreamHandler.seen_host, "localhost:3100")

    def test_html_and_empty_streams_fail_without_destination(self):
        for mode in ("html", "empty"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                StreamHandler.mode = mode
                output = Path(directory) / "bundle.jsonl"
                result = self.run_capture(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
                self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_wrapper_forwards_child_options_after_separator(self):
        with tempfile.TemporaryDirectory() as directory:
            StreamHandler.mode = "valid"
            output = Path(directory) / "bundle.jsonl"
            result = self.run_capture(output, wrapper=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())

    def test_sparse_scoped_history_does_not_wait_for_global_watermark(self):
        with tempfile.TemporaryDirectory() as directory:
            StreamHandler.mode = "sparse"
            output = Path(directory) / "bundle.jsonl"
            result = self.run_capture(output)
            self.assertEqual(result.returncode, 0, result.stderr)
            footer = json.loads(output.read_text().splitlines()[-1])
            self.assertEqual(footer["pages"], 1)
            self.assertEqual(footer["evidence_events"], 1)


if __name__ == "__main__":
    unittest.main()
