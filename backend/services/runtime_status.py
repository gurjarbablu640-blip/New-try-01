"""Read-only health and registration diagnostics for the Celery runtime."""

from __future__ import annotations

from typing import Any, Iterable

from celery_app import CELERY_AVAILABLE, CELERY_IMPORT_ERROR, EXPECTED_TASKS, celery_app


def _registered_tasks(app: Any) -> set[str]:
    return set((getattr(app, "tasks", {}) or {}).keys())


def probe_worker(inspector: Any | None) -> dict[str, Any]:
    """Return worker reachability from a supplied Celery inspector."""
    if inspector is None:
        return {"status": "not_probed", "nodes": []}
    try:
        replies = inspector.ping() or {}
        nodes = sorted(replies)
        return {"status": "healthy" if nodes else "unavailable", "nodes": nodes, "reply_count": len(nodes)}
    except Exception as exc:
        return {"status": "error", "nodes": [], "error": f"{type(exc).__name__}: {exc}"}


def get_runtime_status(
    app: Any = celery_app,
    *,
    worker_inspector: Any | None = None,
    deployment_services: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable report without queueing work or calling providers."""
    registered = _registered_tasks(app)
    missing = sorted(set(EXPECTED_TASKS) - registered) if CELERY_AVAILABLE else list(EXPECTED_TASKS)
    schedule = getattr(getattr(app, "conf", None), "beat_schedule", {}) or {}
    services = set(deployment_services or ())
    worker = probe_worker(worker_inspector)
    beat = {
        "status": "configured" if schedule else "not_configured",
        "schedule_entries": sorted(schedule),
        "service_present": "celery-worker" in services or "celery-beat" in services,
    }
    registration_status = "ok" if not missing and CELERY_AVAILABLE else "failed"
    overall = "ok" if registration_status == "ok" and worker["status"] in {"healthy", "not_probed"} else "degraded"
    from config import settings
    return {
        "status": overall,
        "celery": {
            "available": CELERY_AVAILABLE,
            "import_error": CELERY_IMPORT_ERROR,
            "registration_status": registration_status,
            "registered_tasks": sorted(registered & set(EXPECTED_TASKS)),
            "missing_tasks": missing,
        },
        "worker": worker,
        "beat": beat,
        "safety": {"outbound_test_mode": bool(settings.OUTBOUND_TEST_MODE), "tasks_queued": False, "providers_called": False},
    }


check_celery_runtime = get_runtime_status
