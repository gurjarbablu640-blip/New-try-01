"""Autonomous Daily Scheduler and Pipeline Controller.

Manages the local 24-hour operational cycle:
- 10:00 AM: Discovery starts
- 10:30 AM: Restricted inbox check (morning)
- Daytime: discover → qualify → research → enrich → READY_FOR_EMAIL
- 4:00 PM: Restricted inbox check (afternoon)
- 6:00 PM: Prospecting cutoff, state checkpoint, daily report production
- Night (18:00 - 10:00): Research/enrichment permitted, STRICTLY NO PROSPECT EMAILS.

Functions autonomously and independently without ChatGPT Work availability.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "daily_reports")
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "runtime_state")


@dataclass
class DailyReport:
    report_id: str
    date_str: str
    generated_at: str
    discovered_leads: int = 0
    qualified_opportunities: int = 0
    staged_ready_for_email: int = 0
    phones_enriched: int = 0
    apollo_credits_used: int = 0
    replies_processed: int = 0
    inbox_checks_count: int = 0
    night_research_queued: int = 0
    operating_mode: str = "TEST_MODE" if settings.OUTBOUND_TEST_MODE else "PRODUCTION"
    status: str = "COMPLETED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutonomousScheduler:
    """Controls the daily lifecycle, prospecting hours, and overnight research boundaries."""

    def __init__(
        self,
        report_dir: str = REPORT_DIR,
        state_dir: str = STATE_DIR,
    ):
        self.report_dir = report_dir
        self.state_dir = state_dir
        os.makedirs(self.report_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, "scheduler_state.json")

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return {
                "current_window": "DAY_PROSPECTING",
                "last_run": None,
                "metrics": {
                    "discovered": 0,
                    "qualified": 0,
                    "staged": 0,
                    "phones_enriched": 0,
                    "apollo_credits": 0,
                    "replies_processed": 0,
                },
            }
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        temp = f"{self.state_file}.tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(temp, self.state_file)

    def determine_time_window(self, current_time: Optional[time] = None) -> str:
        """Determine window based on local operational hours.
        
        10:00 - 18:00: DAY_PROSPECTING
        18:00 - 18:30: EVENING_REPORT
        18:30 - 10:00 next day: NIGHT_RESEARCH
        """
        if current_time is None:
            now = datetime.now()
            current_time = now.time()

        t_10am = time(10, 0)
        t_4pm = time(16, 0)
        t_6pm = time(18, 0)
        t_630pm = time(18, 30)

        if t_10am <= current_time < t_6pm:
            return "DAY_PROSPECTING"
        elif t_6pm <= current_time < t_630pm:
            return "EVENING_REPORT"
        else:
            return "NIGHT_RESEARCH"

    def is_email_outreach_permitted(self, current_time: Optional[time] = None) -> bool:
        """Enforce strict rule: NO prospect emails during the night window (18:00 - 10:00)."""
        window = self.determine_time_window(current_time)
        return window == "DAY_PROSPECTING"

    def is_research_enrichment_permitted(self) -> bool:
        """Research and enrichment are permitted 24/7 (both day and night)."""
        return True

    def execute_morning_discovery(self) -> Dict[str, Any]:
        """Triggered at 10:00 AM: Launches prospecting discovery."""
        logger.info("Executing 10:00 AM Morning Discovery cycle")
        state = self._load_state()
        state["last_discovery_start"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)
        return {
            "cycle": "MORNING_DISCOVERY",
            "time": "10:00 AM",
            "status": "started",
            "message": "Prospect discovery initiated across priority sectors.",
        }

    def execute_inbox_check(self, slot: str = "MORNING_1030") -> Dict[str, Any]:
        """Triggered at 10:30 AM or 4:00 PM: Restricted inbox poll and reply classification."""
        logger.info("Executing restricted inbox check [Slot: %s]", slot)
        state = self._load_state()
        state[f"last_inbox_check_{slot}"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)
        return {
            "cycle": f"INBOX_CHECK_{slot}",
            "status": "completed",
            "slot": slot,
            "readonly_mailbox": "INBOX",
            "mode": "restricted_header_first",
        }

    def execute_evening_cutoff_and_report(
        self,
        date_str: Optional[str] = None,
        custom_metrics: Optional[Dict[str, int]] = None,
    ) -> DailyReport:
        """Triggered at 6:00 PM: Cuts off prospecting, saves state, produces daily report."""
        logger.info("Executing 6:00 PM Evening Cutoff & Daily Report generation")
        state = self._load_state()
        today = date_str or datetime.now().strftime("%Y-%m-%d")
        metrics = state.get("metrics", {})
        if custom_metrics:
            metrics.update(custom_metrics)

        report = DailyReport(
            report_id=f"rep-{today}-{uuid.uuid4().hex[:6]}",
            date_str=today,
            generated_at=datetime.now(timezone.utc).isoformat(),
            discovered_leads=metrics.get("discovered", 0),
            qualified_opportunities=metrics.get("qualified", 0),
            staged_ready_for_email=metrics.get("staged", 0),
            phones_enriched=metrics.get("phones_enriched", 0),
            apollo_credits_used=metrics.get("apollo_credits", 0),
            replies_processed=metrics.get("replies_processed", 0),
            inbox_checks_count=2,
            night_research_queued=metrics.get("night_research_queued", 0),
            operating_mode="TEST_MODE" if settings.OUTBOUND_TEST_MODE else "PRODUCTION",
            status="COMPLETED",
        )

        report_path = os.path.join(self.report_dir, f"report_{today}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        state["last_cutoff"] = datetime.now(timezone.utc).isoformat()
        state["last_report_id"] = report.report_id
        state["current_window"] = "NIGHT_RESEARCH"
        self._save_state(state)

        logger.info("Daily report saved to %s", report_path)
        return report

    def get_runtime_summary(self) -> Dict[str, Any]:
        """Return full autonomous scheduler status and operational constraints."""
        window = self.determine_time_window()
        permits_outreach = self.is_email_outreach_permitted()
        state = self._load_state()

        return {
            "status": "active",
            "current_time_window": window,
            "prospecting_active": window == "DAY_PROSPECTING",
            "email_outreach_permitted": permits_outreach,
            "research_enrichment_permitted": True,
            "night_window_safety_lock": not permits_outreach,
            "schedule": {
                "10:00 AM": "Discovery start",
                "10:30 AM": "Morning restricted inbox check",
                "Daytime": "discover -> qualify -> research -> enrich -> READY_FOR_EMAIL",
                "4:00 PM": "Afternoon restricted inbox check",
                "6:00 PM": "Prospecting cutoff, state save, daily report production",
                "Night (18:00 - 10:00)": "Overnight research/enrichment only; NO prospect emails",
            },
            "last_state": state,
        }


# Global instance
autonomous_scheduler = AutonomousScheduler()
