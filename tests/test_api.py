import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app
from src.config import SETTINGS
from src.generate_sample_data import generate

client = TestClient(app)


def _wait_until_finished(run_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


def _sample_csv_files(tmp: Path) -> list[tuple]:
    sample_dir = tmp / "sample"
    generate(sample_dir, seed=42)
    files = []
    for csv_path in sorted(sample_dir.glob("*.csv")):
        files.append(("files", (csv_path.name, csv_path.read_bytes(), "text/csv")))
    return files


class TestHealth(unittest.TestCase):
    def test_health_ok(self):
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


class TestCreateRunValidation(unittest.TestCase):
    def test_no_files_rejected(self):
        # an empty `files` list means the required multipart field is absent entirely --
        # FastAPI's own validation rejects this with 422 before our handler runs.
        resp = client.post("/runs", data={"provider": "mock"}, files=[])
        self.assertEqual(resp.status_code, 422)

    def test_non_csv_file_rejected(self):
        resp = client.post("/runs", files=[("files", ("data.txt", b"not a csv", "text/plain"))])
        self.assertEqual(resp.status_code, 400)
        self.assertIn(".csv", resp.json()["detail"])

    def test_unknown_provider_rejected(self):
        resp = client.post("/runs", data={"provider": "not-a-real-provider"}, files=[("files", ("a.csv", b"x,y\n1,2\n", "text/csv"))])
        self.assertEqual(resp.status_code, 400)

    def test_too_many_files_rejected(self):
        files = [("files", (f"f{i}.csv", b"x\n1\n", "text/csv")) for i in range(11)]
        resp = client.post("/runs", data={"provider": "mock"}, files=files)
        self.assertEqual(resp.status_code, 400)

    def test_bad_csv_content_rejected_synchronously(self):
        # a single column with a lone quote breaks the CSV parser
        resp = client.post("/runs", data={"provider": "mock"}, files=[("files", ("bad.csv", b'"unterminated', "text/csv"))])
        self.assertEqual(resp.status_code, 400)


class TestUnknownRun(unittest.TestCase):
    def test_unknown_run_id_is_404(self):
        resp = client.get("/runs/000000000000")
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_like_run_id_is_404_not_500(self):
        resp = client.get("/runs/..%2f..%2fetc")
        self.assertIn(resp.status_code, (404, 422))

    def test_report_for_unknown_run_is_404(self):
        resp = client.get("/runs/000000000000/report")
        self.assertEqual(resp.status_code, 404)


class TestFullRunLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.created_run_ids = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        for run_id in self.created_run_ids:
            shutil.rmtree(SETTINGS.runs_dir / run_id, ignore_errors=True)
            shutil.rmtree(SETTINGS.upload_dir / run_id, ignore_errors=True)
            shutil.rmtree(SETTINGS.sandbox_root / run_id, ignore_errors=True)

    def _post_run(self, **kwargs):
        resp = client.post("/runs", **kwargs)
        if resp.status_code == 202:
            self.created_run_ids.append(resp.json()["run_id"])
        return resp

    def test_mock_run_completes_and_report_is_fetchable(self):
        resp = self._post_run(data={"provider": "mock"}, files=_sample_csv_files(self.tmp))
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        run_id = body["run_id"]
        self.assertEqual(body["status"], "pending")
        self.assertIn("orders", body["row_counts"])

        final = _wait_until_finished(run_id)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["findings"], 2)
        self.assertGreaterEqual(final["citations_passed"], 1)

        report = client.get(f"/runs/{run_id}/report")
        self.assertEqual(report.status_code, 200)
        self.assertIn("executive_summary", report.json())

        html_resp = client.get(f"/runs/{run_id}/report.html")
        self.assertEqual(html_resp.status_code, 200)
        self.assertIn("Business Analytics Report", html_resp.text)

    def test_default_provider_is_mock(self):
        resp = self._post_run(files=_sample_csv_files(self.tmp))
        self.assertEqual(resp.status_code, 202)
        final = _wait_until_finished(resp.json()["run_id"])
        self.assertEqual(final["status"], "done")

    def test_provider_failure_recorded_as_failed_status_not_500(self):
        resp = self._post_run(data={"provider": "openai"}, files=_sample_csv_files(self.tmp))
        self.assertEqual(resp.status_code, 202)
        final = _wait_until_finished(resp.json()["run_id"])
        self.assertEqual(final["status"], "failed")
        self.assertIn("OPENAI_API_KEY", final["error"])

    def test_chart_endpoint_404_when_no_chart_exists(self):
        resp = self._post_run(data={"provider": "mock"}, files=_sample_csv_files(self.tmp))
        run_id = resp.json()["run_id"]
        _wait_until_finished(run_id)
        chart_resp = client.get(f"/runs/{run_id}/charts/chart_deadbeef.png")
        self.assertEqual(chart_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
