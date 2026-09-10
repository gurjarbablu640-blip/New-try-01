"""Celery application configuration and registration diagnostics."""

from config import settings

EXPECTED_TASKS = (
    "workers.triggerEngine.scan_naukri_jobs",
    "workers.triggerEngine.scan_google_news",
    "workers.triggerEngine.check_nabl_renewals",
    "workers.triggerEngine.check_iso_audit_windows",
    "workers.triggerEngine.detect_import_spikes",
    "workers.triggerEngine.mine_google_reviews",
    "services.lookalikeEngine.find_lookalikes",
    "services.icpLearner.learn_icp_patterns",
    "services.buyingWindow.calculate_buying_windows",
    "services.abOptimizer.analyze_ab_results",
)

TASK_MODULES = [
    "workers.triggerEngine",
    "services.lookalikeEngine",
    "services.icpLearner",
    "services.buyingWindow",
    "services.abOptimizer",
]

CELERY_AVAILABLE = False
CELERY_IMPORT_ERROR = None

try:
    from celery import Celery
    from celery.schedules import crontab

    celery_app = Celery(
        "salesoorja",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=TASK_MODULES,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Kolkata",
        enable_utc=True,
    )
    celery_app.conf.beat_schedule = {
        "trigger-engine-naukri": {"task": EXPECTED_TASKS[0], "schedule": crontab(minute=0, hour="*/6")},
        "trigger-engine-news": {"task": EXPECTED_TASKS[1], "schedule": crontab(minute=15, hour="*/6")},
        "trigger-engine-nabl-renewal": {"task": EXPECTED_TASKS[2], "schedule": crontab(minute=0, hour=7)},
        "trigger-engine-iso-audit": {"task": EXPECTED_TASKS[3], "schedule": crontab(minute=30, hour="*/6")},
        "trigger-engine-import-spike": {"task": EXPECTED_TASKS[4], "schedule": crontab(minute=45, hour="*/6")},
        "trigger-engine-reviews": {"task": EXPECTED_TASKS[5], "schedule": crontab(minute=0, hour=3)},
        "lookalike-engine": {"task": EXPECTED_TASKS[6], "schedule": crontab(minute=0, hour=6)},
        "icp-learning": {"task": EXPECTED_TASKS[7], "schedule": crontab(minute=0, hour=0, day_of_week=0)},
        "buying-window-calc": {"task": EXPECTED_TASKS[8], "schedule": crontab(minute=0, hour=5)},
        "ab-analysis": {"task": EXPECTED_TASKS[9], "schedule": crontab(minute=0, hour=0, day_of_week=1)},
    }
    try:
        celery_app.loader.import_default_modules()
    except Exception:
        pass

    @celery_app.task(name="salesoorja.test_ping")
    def test_ping():
        """Harmless diagnostic task for runtime verification."""
        from datetime import datetime
        return {"status": "pong", "timestamp": datetime.utcnow().isoformat(), "safety": "verified"}

    CELERY_AVAILABLE = True
except Exception as exc:
    CELERY_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

    class DummyCelery:
        conf = type("DummyConf", (), {"beat_schedule": {}})()

        def task(self, *args, **kwargs):
            def decorator(function):
                raise RuntimeError(f"Celery unavailable; refusing to register task {function.__name__}: {CELERY_IMPORT_ERROR}")
            return decorator

    celery_app = DummyCelery()
