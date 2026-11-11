"""HTTP-level tests: a real ThreadingHTTPServer on 127.0.0.1 with a temporary store.

The adapter tests in test_webserver.py cover the op_* functions; these exercise the
request path itself (routing, body parsing, status codes, persistence) the way a
browser or curl would see it.
"""
import http.client
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

from tasklistprogram import webserver as ws
from tasklistprogram.core import model

REPO_ROOT = Path(__file__).resolve().parent.parent


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).strftime("%Y-%m-%d")


class ServerTestCase(unittest.TestCase):
    """Starts one server per test on a free port with an empty temp data directory."""
    PATHS = ("DATA_DIR", "DB_FILE", "DATA_FILE", "BACKUP_FILE", "BACKUP_DIR",
             "LEGACY_DATA_FILE", "LEGACY_BACKUP_FILE")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = {k: getattr(model, k) for k in self.PATHS}
        model.set_data_dir(self.tmp)
        model.LEGACY_DATA_FILE = self.tmp / "no-legacy.json"
        model.LEGACY_BACKUP_FILE = self.tmp / "no-legacy.bak"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ws.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        for k, v in self._orig.items():
            setattr(model, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def request(self, method, path, body=None, headers=None, raw=None):
        """Send one request. `body` is JSON-encoded; `raw` bytes are sent as given.

        Returns (status, decoded JSON or text, response headers).
        """
        hdrs = {} if headers is None else dict(headers)
        data = None
        if raw is not None:
            data = raw
            hdrs.setdefault("Content-Type", "application/json")
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            payload = resp.read()
            ctype = resp.getheader("Content-Type", "")
            if ctype.startswith("application/json"):
                decoded = json.loads(payload.decode("utf-8"))
            else:
                decoded = payload.decode("utf-8", errors="replace")
            return resp.status, decoded, resp.headers
        finally:
            conn.close()

    def add(self, **fields):
        status, task, _ = self.request("POST", "/api/tasks", fields)
        self.assertEqual(status, 201, task)
        return task


class StaticAndRoutingTests(ServerTestCase):
    def test_index_is_served(self):
        status, text, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("Tiny Tasklist", text)

    def test_unknown_static_file_is_404(self):
        status, _, _ = self.request("GET", "/nonexistent.js")
        self.assertEqual(status, 404)

    def test_static_files_cannot_escape_into_a_sibling_with_the_same_prefix(self):
        from unittest.mock import patch
        web = self.tmp / "web"
        web.mkdir()
        sibling = self.tmp / "web-extra"
        sibling.mkdir()
        (sibling / "example.txt").write_text("outside the served folder", encoding="utf-8")
        with patch.object(ws, "WEB_DIR", web):
            status, _, _ = self.request("GET", "/../web-extra/example.txt")
        self.assertEqual(status, 404)

    def test_unknown_api_route_is_404(self):
        status, body, _ = self.request("POST", "/api/nothing", {})
        self.assertEqual(status, 404)
        self.assertEqual(body, {"error": "not found"})

    def test_bad_and_missing_ids(self):
        self.assertEqual(self.request("POST", "/api/tasks/abc/toggle")[0], 400)
        self.assertEqual(self.request("POST", "/api/tasks/999/toggle")[0], 404)
        self.assertEqual(self.request("DELETE", "/api/tasks/")[0], 400)


class RecurrenceCatchUpTests(ServerTestCase):
    """The server, not only the desktop app, must roll overdue repeating tasks forward."""

    def test_listing_catches_up_an_overdue_daily_habit(self):
        self.add(title="Daily habit", due="-3d", repeat="daily", priority="D")
        status, body, _ = self.request("GET", "/api/tasks")
        self.assertEqual(status, 200)
        t = body["tasks"][0]
        self.assertEqual(t["due"], iso(0))
        # Three missed occurrences, hazard escalation on by default: Ultra.
        self.assertEqual(t["skip_count"], 3)
        self.assertEqual(t["priority"], "U")

    def test_catch_up_is_saved_once_and_then_idempotent(self):
        self.add(title="Daily habit", due="-3d", repeat="daily", priority="D")
        self.request("GET", "/api/tasks")
        rev_after_first = model.current_rev()
        self.request("GET", "/api/tasks")
        self.assertEqual(model.current_rev(), rev_after_first)
        status, body, _ = self.request("GET", "/api/tasks")
        self.assertEqual(body["tasks"][0]["due"], iso(0))

    def test_one_completion_lands_on_the_next_future_occurrence(self):
        t = self.add(title="Daily habit", due="-3d", repeat="daily", priority="D")
        self.request("GET", "/api/tasks")
        status, done, _ = self.request("POST", f"/api/tasks/{t['id']}/toggle")
        self.assertEqual(status, 200)
        self.assertFalse(done["done"])
        self.assertEqual(done["due"], iso(1))
        self.assertEqual(done["history"], [iso(0)])
        self.assertEqual(done["times"], 1)
        self.assertEqual(done["skip_count"], 0)
        self.assertEqual(done["priority"], "D")  # escalation cleared, base priority restored

    def test_completion_without_a_prior_listing_also_lands_in_the_future(self):
        t = self.add(title="Weekly review", due="-10d", repeat="weekly")
        status, done, _ = self.request("POST", f"/api/tasks/{t['id']}/done")
        self.assertEqual(status, 200)
        self.assertEqual(done["due"], iso(4))  # -10d, -3d, then +4d is the first future date
        self.assertEqual(len(done["history"]), 1)

    def test_future_task_is_left_alone(self):
        self.add(title="Later", due="+3d", repeat="daily")
        status, body, _ = self.request("GET", "/api/tasks")
        self.assertEqual(body["tasks"][0]["due"], iso(3))
        self.assertEqual(body["tasks"][0]["skip_count"], 0)


class RequestValidationTests(ServerTestCase):
    """Malformed and cross-site requests get a JSON error, never a dropped connection."""

    def test_malformed_json_is_400(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b"{bad json")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "invalid JSON body"})

    def test_non_object_body_is_400(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b"[1, 2]")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "JSON body must be an object"})

    def test_bad_content_length_is_400(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b"{}", headers={"Content-Length": "abc"})
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "invalid Content-Length"})

    def test_oversized_body_is_413(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b"{}",
                                       headers={"Content-Length": str(ws.MAX_BODY_BYTES + 1)})
        self.assertEqual(status, 413)

    def test_empty_body_still_reports_missing_title(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b"")
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "title required"})

    def test_non_json_content_type_is_415(self):
        status, body, _ = self.request("POST", "/api/tasks", raw=b'{"title": "x"}',
                                       headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"], [])

    def test_cross_site_origin_is_403(self):
        status, body, _ = self.request("POST", "/api/tasks", {"title": "x"},
                                       headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"], [])

    def test_cross_site_referer_is_403(self):
        status, _, _ = self.request("POST", "/api/tasks", {"title": "x"},
                                    headers={"Referer": "http://evil.example/page"})
        self.assertEqual(status, 403)

    def test_cross_site_bodiless_hard_delete_is_403(self):
        t = self.add(title="keep me")
        status, _, _ = self.request("POST", f"/api/tasks/{t['id']}/harddelete",
                                    headers={"Origin": "http://evil.example", "Content-Type": "text/plain"})
        self.assertEqual(status, 403)
        self.assertEqual(len(self.request("GET", "/api/tasks")[1]["tasks"]), 1)

    def test_own_origin_is_accepted(self):
        for host in ("127.0.0.1", "localhost"):
            origin = f"http://{host}:{self.port}"
            status, _, _ = self.request("POST", "/api/tasks", {"title": host},
                                        headers={"Origin": origin, "Referer": origin + "/"})
            self.assertEqual(status, 201, origin)

    def test_same_host_other_port_is_rejected(self):
        status, _, _ = self.request("POST", "/api/tasks", {"title": "x"},
                                    headers={"Origin": f"http://127.0.0.1:{self.port + 1}"})
        self.assertEqual(status, 403)

    def test_bodiless_requests_need_no_content_type(self):
        t = self.add(title="curl style")
        self.assertEqual(self.request("POST", f"/api/tasks/{t['id']}/toggle")[0], 200)
        self.assertEqual(self.request("DELETE", f"/api/tasks/{t['id']}")[0], 200)

    def test_invalid_due_is_400_with_import_wording(self):
        status, body, _ = self.request("POST", "/api/tasks", {"title": "Bad due", "due": "notadate"})
        self.assertEqual(status, 400)
        self.assertTrue(body["error"].startswith("invalid due 'notadate'. Use YYYY-MM-DD"), body)
        self.assertEqual(self.request("GET", "/api/tasks")[1]["tasks"], [])

    def test_invalid_repeat_is_400(self):
        status, body, _ = self.request("POST", "/api/tasks", {"title": "x", "repeat": "fortnightly"})
        self.assertEqual(status, 400)
        self.assertTrue(body["error"].startswith("invalid repeat 'fortnightly'. Use none/daily"), body)

    def test_patch_with_invalid_values_is_400_and_leaves_task_unchanged(self):
        t = self.add(title="stable", due="+30d", repeat="weekly")  # future, so no catch-up
        status, body, _ = self.request("PATCH", f"/api/tasks/{t['id']}", {"due": "notadate"})
        self.assertEqual(status, 400)
        self.assertIn("invalid due", body["error"])
        status, body, _ = self.request("PATCH", f"/api/tasks/{t['id']}", {"repeat": "fortnightly"})
        self.assertEqual(status, 400)
        self.assertIn("invalid repeat", body["error"])
        current = self.request("GET", "/api/tasks")[1]["tasks"][0]
        self.assertEqual((current["due"], current["repeat"]), (iso(30), "weekly"))

    def test_import_text_must_be_a_string(self):
        status, body, _ = self.request("POST", "/api/import", {"text": 5})
        self.assertEqual(status, 400)
        self.assertEqual(body, {"error": "text must be a string"})


class PersistenceTests(ServerTestCase):
    def test_task_survives_a_fresh_load(self):
        t = self.add(title="Persist me", due="tomorrow", priority="H", group="Demo")
        self.assertEqual(t["due"], iso(1))
        db = model.load_db()  # what a restarted server would read
        self.assertEqual([x["title"] for x in db["tasks"]], ["Persist me"])
        self.assertEqual(db["tasks"][0]["group"], "Demo")

    def test_soft_delete_and_restore(self):
        t = self.add(title="Trash me")
        status, deleted, _ = self.request("DELETE", f"/api/tasks/{t['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["is_deleted"])
        status, restored, _ = self.request("PATCH", f"/api/tasks/{t['id']}", {"is_deleted": False})
        self.assertFalse(restored["is_deleted"])

    def test_hard_delete_removes_the_row(self):
        t = self.add(title="Gone")
        self.assertEqual(self.request("POST", f"/api/tasks/{t['id']}/harddelete")[0], 200)
        self.assertEqual(self.request("POST", f"/api/tasks/{t['id']}/harddelete")[0], 404)
        self.assertEqual(model.load_db()["tasks"], [])

    def test_import_reports_added_and_failed_lines(self):
        text = "Demo import | due: tomorrow | prio: M\nBroken | due: notadate\n# comment"
        status, body, _ = self.request("POST", "/api/import", {"text": text})
        self.assertEqual(status, 200)
        self.assertEqual((body["added"], body["failed"]), (1, 1))
        self.assertIn("invalid due 'notadate'", body["details"][0])


class CommandLineTests(unittest.TestCase):
    """`python -m tasklistprogram.webserver` as a visitor would run it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        return subprocess.Popen(
            [sys.executable, "-m", "tasklistprogram.webserver", *args],
            cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def _start(self):
        proc = self._run("--port", "0", "--data-dir", str(self.tmp))
        line = proc.stdout.readline()
        match = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        if not match:
            proc.kill()
            self.fail(f"no address line, got {line!r}; stderr: {proc.stderr.read()}")
        return proc, int(match.group(1))

    def _stop(self, proc):
        proc.terminate()
        proc.wait(timeout=10)

    def _get_json(self, port, path):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read().decode("utf-8"))
        finally:
            conn.close()

    def test_port_zero_and_data_dir_and_persistence_across_restart(self):
        proc, port = self._start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/")
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("POST", "/api/tasks", body=json.dumps({"title": "Survives restart"}),
                         headers={"Content-Type": "application/json"})
            self.assertEqual(conn.getresponse().status, 201)
            conn.close()
        finally:
            self._stop(proc)
        self.assertTrue((self.tmp / "tasks.db").exists())
        proc, port = self._start()
        try:
            status, body = self._get_json(port, "/api/tasks")
            self.assertEqual(status, 200)
            self.assertEqual([t["title"] for t in body["tasks"]], ["Survives restart"])
        finally:
            self._stop(proc)

    def test_bad_port_value_is_a_usage_error_not_a_traceback(self):
        proc = self._run("--port", "notaport")
        _, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid int value", err)
        self.assertNotIn("Traceback", err)

    def test_port_in_use_is_reported_without_a_traceback(self):
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        try:
            proc = self._run("--port", str(blocker.getsockname()[1]), "--data-dir", str(self.tmp))
            _, err = proc.communicate(timeout=30)
        finally:
            blocker.close()
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(err.startswith("Could not listen on 127.0.0.1:"), err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
