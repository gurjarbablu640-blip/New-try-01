import unittest
from types import SimpleNamespace

from services.runtime_status import get_runtime_status, probe_worker


class FakeInspector:
    def __init__(self, replies=None, error=None):
        self.replies, self.error = replies, error

    def ping(self):
        if self.error:
            raise self.error
        return self.replies


class RuntimeStatusTests(unittest.TestCase):
    def test_status_reports_missing_tasks_and_no_side_effects(self):
        app = SimpleNamespace(tasks={"workers.triggerEngine.scan_naukri_jobs": object()}, conf=SimpleNamespace(beat_schedule={"trigger": object()}))
        report = get_runtime_status(app, deployment_services=[])
        self.assertEqual(report["celery"]["registration_status"], "failed")
        self.assertIn("services.abOptimizer.analyze_ab_results", report["celery"]["missing_tasks"])
        self.assertFalse(report["safety"]["tasks_queued"])
        self.assertFalse(report["safety"]["providers_called"])
        self.assertFalse(report["beat"]["service_present"])

    def test_worker_probe_reports_nodes(self):
        self.assertEqual(probe_worker(FakeInspector({"worker-a": {"ok": "pong"}})), {"status": "healthy", "nodes": ["worker-a"], "reply_count": 1})

    def test_worker_probe_surfaces_failures(self):
        report = probe_worker(FakeInspector(error=ConnectionError("redis down")))
        self.assertEqual(report["status"], "error")
        self.assertIn("redis down", report["error"])

    def test_live_celery_registration_and_ping(self):
        from celery_app import celery_app, CELERY_AVAILABLE
        if not CELERY_AVAILABLE:
            self.skipTest("Celery not installed or failed to import")
        report = get_runtime_status(celery_app, deployment_services=["celery-worker", "celery-beat"])
        self.assertEqual(report["celery"]["registration_status"], "ok")
        self.assertEqual(report["celery"]["missing_tasks"], [])
        self.assertTrue(report["beat"]["service_present"])
        self.assertIn("salesoorja.test_ping", celery_app.tasks)
        # Verify harmless ping execution directly
        ping_fn = celery_app.tasks["salesoorja.test_ping"]
        res = ping_fn()
        self.assertEqual(res.get("status"), "pong")
        self.assertEqual(res.get("safety"), "verified")


if __name__ == "__main__":
    unittest.main()

