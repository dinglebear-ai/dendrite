"""Execute the shell's inline script against a stubbed DOM.

A hoisting bug once made `help` undefined at the line that attached its
listener, and the TypeError killed every handler after it — search, drawer,
theme, expand state. Sixty-five unit tests, the linter and a screenshot all
looked fine, because the markup was correct and only the behaviour was dead.

This runs the real script in node against a DOM stub that is permissive about
everything except identity: `getElementById` returns an element only for ids
that actually exist in the rendered page, and `querySelector` only for
selectors the page really contains. Anything the script then calls on a missing
element throws, exactly as it does in a browser.

Skipped when node is unavailable. Not a browser test — it exercises no layout,
no events and no real DOM semantics — but it covers the failure mode that
reached production twice.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _app.shell import render_shell  # noqa: E402

NODE = shutil.which("node")

ARTIFACT = (
    '<!doctype html><html lang="en"><head><title>Core — Demo</title>'
    "<style>:root{--b1:#fff;--bc:#111;--mono:monospace;--body:sans-serif}</style></head>"
    '<body><div class="shell"><header class="top">chrome</header><main>'
    '<div class="eyebrow">Area / thing</div><p>Description.</p>'
    '<details class="issue"><summary><h3>First</h3>'
    '<span class="tag high">High</span></summary>body</details>'
    '<details class="issue"><summary><h3>Second</h3>'
    '<span class="tag runtime">Runtime</span></summary>body</details>'
    "</main></div></body></html>"
)

HARNESS = r"""
const ids = new Set(IDS);
const selectors = new Set(SELECTORS);

const nodeStub = (name) => new Proxy(function () {}, {
  get(target, prop) {
    if (prop === "then") return undefined;                 // not a promise
    if (prop === "dataset" || prop === "classList" || prop === "style") return nodeStub(name + "." + prop);
    if (prop === "textContent" || prop === "value" || prop === "innerHTML") return "";
    if (prop === "hidden" || prop === "open" || prop === "checked") return false;
    if (prop === "length") return 0;
    if (prop === "href") return "#x";
    if (prop === "parentElement" || prop === "target") return nodeStub(name + "." + prop);
    return nodeStub(name + "." + String(prop));
  },
  apply() { return nodeStub(name + "()"); },
  set() { return true; },
});

const listStub = (n) => {
  const items = Array.from({ length: n }, (_, i) => nodeStub("item" + i));
  items.forEach = Array.prototype.forEach.bind(items);
  return items;
};

globalThis.document = {
  documentElement: nodeStub("html"),
  body: nodeStub("body"),
  // Identity is the one thing the stub is strict about.
  getElementById: (id) => (ids.has(id) ? nodeStub("#" + id) : null),
  querySelector: (sel) => (selectors.has(sel) ? nodeStub(sel) : null),
  querySelectorAll: (sel) => listStub(selectors.has(sel) ? 2 : 0),
  addEventListener: () => {},
  createElement: () => nodeStub("el"),
  fonts: { ready: Promise.resolve(), check: () => true },
};
globalThis.window = {
  addEventListener: () => {},
  IntersectionObserver: function () { this.observe = () => {}; },
  AbortController: function () { this.abort = () => {}; this.signal = {}; },
  matchMedia: () => ({ matches: false, addEventListener: () => {} }),
};
globalThis.IntersectionObserver = window.IntersectionObserver;
globalThis.AbortController = window.AbortController;
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.location = { hash: "", href: "/", origin: "http://x", pathname: "/a.html" };
// node defines navigator read-only; redefine rather than assign.
Object.defineProperty(globalThis, "navigator", {
  value: { clipboard: { writeText: () => Promise.resolve() } }, configurable: true });
globalThis.fetch = () => Promise.resolve({ json: () => Promise.resolve({ query: "", results: [] }) });
globalThis.setTimeout = (fn) => 0;
globalThis.clearTimeout = () => {};
globalThis.encodeURIComponent = encodeURIComponent;

SCRIPT
"""


def _fixture_page():
    item = {"href": "reports/a.html", "title": "A", "status": "accepted", "topic": "t",
            "meta": {}, "related": [], "source": ARTIFACT}
    catalog = {"groups": [{"name": "reports", "items": [item]},
                          {"name": "scripts", "items": []}],
               "items": [item]}
    return render_shell(catalog, item, "clean")


@unittest.skipUnless(NODE, "node is required to execute the shell script")
class ShellScriptTest(unittest.TestCase):
    def setUp(self):
        self.page = _fixture_page()
        self.script = re.search(r"<script>\n(.*?)</script>", self.page, re.S).group(1)

    def _run(self, script):
        ids = sorted(set(re.findall(r'id="([^"]+)"', self.page)))
        selectors = sorted({".wb-cat", ".wb-item", ".wb-out", ".wb-on", ".wb-grid",
                            ".wb-anchor", "details.issue", ".wb-prev", ".wb-next"})
        harness = (HARNESS.replace("IDS", json.dumps(ids))
                          .replace("SELECTORS", json.dumps(selectors))
                          .replace("SCRIPT", script))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harness.mjs"
            path.write_text(harness)
            return subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=30)

    def test_script_parses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "s.js"
            path.write_text("(function(){" + self.script + "})")
            check = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)

    def test_script_runs_without_throwing(self):
        result = self._run(self.script)
        self.assertEqual(result.returncode, 0,
                         "the shell script threw:\n" + result.stderr[-1500:])

    def test_a_listener_on_a_missing_element_is_caught(self):
        # The regression itself: attach to an id the page does not contain.
        broken = self.script.replace(
            'var groups=', 'document.getElementById("wbNotThere").addEventListener("x",function(){});var groups=', 1)
        result = self._run(broken)
        self.assertNotEqual(result.returncode, 0,
                            "the harness must fail when the script touches a missing element")
        self.assertIn("TypeError", result.stderr)


if __name__ == "__main__":
    unittest.main()
