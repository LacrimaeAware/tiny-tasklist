"""Guard against shipping a broken web front-end.

A single JS syntax error makes the whole app.js fail to load (no tasks, dead theme
toggle, etc.) with nothing obvious in the console. If Node is available, lint the
web scripts with `node --check`; otherwise skip.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node not installed; skipping JS syntax check")
class WebJsSyntaxTests(unittest.TestCase):
    def _check(self, name):
        path = WEB / name
        self.assertTrue(path.exists(), f"{name} missing")
        result = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{name} has a syntax error:\n{result.stderr}")

    def test_app_js(self):
        self._check("app.js")

    def test_sample_data_js(self):
        self._check("sample-data.js")


class WebFilesPresentTests(unittest.TestCase):
    def test_core_files_exist(self):
        for f in ("index.html", "styles.css", "app.js", "sample-data.js"):
            self.assertTrue((WEB / f).exists(), f"web/{f} missing")


if __name__ == "__main__":
    unittest.main()
