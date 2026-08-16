"""Celery application configuration."""
try:
    from celery import Celery
    from celery.schedules import crontab
    from config import settings

    celery_app = Celery(
        "salesoorja",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Kolkata",
        enable_utc=True,
    )

    # Beat schedule for periodic tasks
    celery_app.conf.beat_schedule = {
        # Module 8: Buying Trigger Engine - every 6 hours
        "trigger-engine-naukri": {
            "task": "workers.triggerEngine.scan_naukri_jobs",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "trigger-engine-news": {
            "task": "workers.triggerEngine.scan_google_news",
            "schedule": crontab(minute=15, hour="*/6"),
        },
        "trigger-engine-nabl-renewal": {
            "task": "workers.triggerEngine.check_nabl_renewals",
            "schedule": crontab(minute=0, hour=7),  # Daily at 7 AM IST
        },
        "trigger-engine-iso-audit": {
            "task": "workers.triggerEngine.check_iso_audit_windows",
            "schedule": crontab(minute=30, hour="*/6"),
        },
        "trigger-engine-import-spike": {
            "task": "workers.triggerEngine.detect_import_spikes",
            "schedule": crontab(minute=45, hour="*/6"),
        },
        "trigger-engine-reviews": {
            "task": "workers.triggerEngine.mine_google_reviews",
            "schedule": crontab(minute=0, hour=3),  # Daily at 3 AM IST
        },
        # Module 14: Lookalike Engine - daily
        "lookalike-engine": {
            "task": "services.lookalikeEngine.find_lookalikes",
            "schedule": crontab(minute=0, hour=6),  # Daily at 6 AM IST
        },
        # Module 15: ICP Learning - weekly (Sunday midnight)
        "icp-learning": {
            "task": "services.icpLearner.learn_icp_patterns",
            "schedule": crontab(minute=0, hour=0, day_of_week=0),
        },
        # Module 16: Buying Window calculation - daily
        "buying-window-calc": {
            "task": "services.buyingWindow.calculate_buying_windows",
            "schedule": crontab(minute=0, hour=5),  # Daily at 5 AM IST
        },
        # Module 17: A/B analysis - weekly
        "ab-analysis": {
            "task": "services.abOptimizer.analyze_ab_results",
            "schedule": crontab(minute=0, hour=0, day_of_week=1),  # Monday midnight
        },
    }

    celery_app.autodiscover_tasks([
        "workers",
        "services",
    ])
except Exception:
    class DummyCelery:
        def task(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator
    celery_app = DummyCelery()
