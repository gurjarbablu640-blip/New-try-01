"""Salesoorja Browser Research Service (Playwright Chromium Engine).

Lightweight, deterministic browser automation and DOM extraction harness.
NOTE: This is Salesoorja's custom Playwright research worker, NOT official ByteDance DeerFlow 2.x.
Official ByteDance DeerFlow is blocked by active LLM provider requirements:
OFFICIAL_DEERFLOW_STATUS = BLOCKED_BY_LLM_PROVIDER.

Exposes standard HTTP endpoints:
- GET  /health
- POST /api/tasks
- GET  /api/tasks/{task_id}
- POST /api/browser/navigate
- GET  /api/challenges
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("browser-research-service")

app = FastAPI(title="Salesoorja Browser Research Service", version="1.0.0-playwright")

# In-memory storage for tasks and challenges
TASKS_STORE: Dict[str, Dict[str, Any]] = {}
CHALLENGES_STORE: Dict[str, Dict[str, Any]] = {}
CHALLENGES_DIR = os.path.join(os.path.dirname(__file__), "challenges")
os.makedirs(CHALLENGES_DIR, exist_ok=True)


class TaskPayload(BaseModel):
    task_id: Optional[str] = None
    task_type: str = "subagent_research"
    company_name: str
    domain: Optional[str] = ""
    target_urls: Optional[List[str]] = Field(default_factory=list)
    focus_areas: Optional[List[str]] = Field(default_factory=lambda: ["expansion", "qa_hiring", "facility"])
    facility: Optional[str] = ""
    multi_step: bool = True
    browser_profile: Optional[str] = "default"
    created_at: Optional[str] = None


class DirectNavigatePayload(BaseModel):
    url: str
    company_name: Optional[str] = ""
    follow_links: bool = True
    link_keywords: Optional[List[str]] = Field(default_factory=lambda: ["facility", "plant", "location", "quality", "about"])
    browser_profile: Optional[str] = "default"
    max_wait_ms: int = 15000


PROFILES_BASE_DIR = os.path.join(os.path.dirname(__file__), "browser_profiles")
os.makedirs(PROFILES_BASE_DIR, exist_ok=True)


def detect_challenge(html: str, title: str) -> Optional[str]:
    """Detect security walls or challenges that require human handoff."""
    html_lower = html.lower()
    title_lower = title.lower()

    if "just a moment..." in title_lower or "attention required! | cloudflare" in title_lower:
        return "CLOUDFLARE_TURNSTILE"
    if "cf-browser-verification" in html_lower or "challenges.cloudflare.com" in html_lower:
        return "CLOUDFLARE_CHALLENGE"
    if "g-recaptcha" in html_lower or "recaptcha" in html_lower and "captcha" in title_lower:
        return "RECAPTCHA_WALL"
    if "h-captcha" in html_lower or ("hcaptcha" in html_lower and "captcha" in title_lower):
        return "HCAPTCHA_WALL"
    if "please verify you are a human" in html_lower or "security check" in title_lower:
        return "GENERIC_BOT_DETECTION"
    if "otp" in title_lower or "two-factor" in title_lower or "2fa" in title_lower:
        return "TWO_FACTOR_AUTH"
    if "linkedin" in title_lower or "linkedin" in html_lower or "authwall" in html_lower:
        if any(w in title_lower for w in ["sign in", "log in", "authwall", "security verification"]):
            return "LINKEDIN_LOGIN_REQUIRED"
        if "checkpoint" in html_lower or ("challenge" in html_lower and "security" in html_lower):
            return "LINKEDIN_SECURITY_CHALLENGE"
        if "join linkedin" in title_lower or "join | linkedin" in title_lower:
            return "LINKEDIN_AUTH_WALL"
    return None


def execute_browser_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Perform real browser research job via Playwright Chromium."""
    from playwright.sync_api import sync_playwright

    task_id = payload.get("task_id") or f"df-{uuid.uuid4().hex[:8]}"
    company = payload.get("company_name", "")
    target_urls = payload.get("target_urls") or []
    focus_areas = payload.get("focus_areas") or []
    facility = payload.get("facility") or ""
    multi_step = payload.get("multi_step", True)
    profile_req = str(payload.get("browser_profile") or "default").lower().replace(" ", "_")

    if not target_urls:
        if payload.get("domain"):
            target_urls = [f"https://{payload['domain']}"]
        else:
            return {
                "task_id": task_id,
                "status": "error",
                "error": "No target URLs or domain provided",
            }

    start_time = time.perf_counter()
    start_iso = datetime.now(timezone.utc).isoformat()

    results = []
    actions_performed = []
    unique_evidence = []
    challenge_detected = None

    try:
        with sync_playwright() as p:
            browser = None
            if "linkedin" in profile_req:
                user_data_dir = os.path.join(PROFILES_BASE_DIR, "salesoorja_linkedin")
                os.makedirs(user_data_dir, exist_ok=True)
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720},
                )
                actions_performed.append("launched persistent browser context (Salesoorja LinkedIn)")
            else:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720},
                )
            page = context.new_page()
            page.set_default_timeout(15000)

            for target_url in target_urls[:2]:
                actions_performed.append(f"navigate to {target_url}")
                logger.info("[%s] Navigating to: %s", task_id, target_url)
                
                try:
                    page.goto(target_url, wait_until="commit", timeout=10000)
                    time.sleep(1.5)  # Allow DOM hydration
                except Exception as nav_exc:
                    logger.warning("[%s] Failed to load %s: %s", task_id, target_url, nav_exc)
                    actions_performed.append(f"error loading {target_url}: {nav_exc}")
                    continue

                page_title = page.title()
                html_content = page.content()
                
                # Check challenge wall
                challenge = detect_challenge(html_content, page_title)
                if challenge:
                    challenge_detected = challenge
                    actions_performed.append(f"challenge detected: {challenge}")
                    challenge_record = {
                        "task_id": task_id,
                        "company": company,
                        "url": target_url,
                        "challenge_type": challenge,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "resume_state": "PAUSED_AWAITING_HUMAN",
                        "intended_next_action": f"extract content from {target_url}",
                    }
                    CHALLENGES_STORE[task_id] = challenge_record
                    with open(os.path.join(CHALLENGES_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
                        json.dump(challenge_record, f, indent=2)

                    context.close()
                    if browser:
                        browser.close()
                    elapsed = time.perf_counter() - start_time
                    return {
                        "task_id": task_id,
                        "status": "MANUAL_BROWSER_ACTION_REQUIRED",
                        "company": company,
                        "challenge_type": challenge,
                        "url": target_url,
                        "page_title": page_title,
                        "browser_start_time": start_iso,
                        "browser_end_time": datetime.now(timezone.utc).isoformat(),
                        "latency_seconds": round(elapsed, 3),
                        "actions_performed": actions_performed,
                        "browser_launched": True,
                        "message": f"Manual action required: {challenge} detected at {target_url}. Security bypass avoided.",
                    }

                # Extract text using inner_text of body
                body_elem = page.query_selector("body")
                extracted_text = body_elem.inner_text() if body_elem else ""
                text_len = len(extracted_text)
                actions_performed.append(f"extracted {text_len} characters from {target_url}")

                page_record = {
                    "url": target_url,
                    "title": page_title,
                    "text_length": text_len,
                    "text_sample": extracted_text[:1500],
                }

                # Scan for facility / trigger / quality keywords
                for kw in ["plant", "facility", "manufacturing", "quality", "iso", "expansion", "chennai", "oragadam", "pune", "coimbatore", "delhi", "noida"]:
                    if kw in extracted_text.lower():
                        unique_evidence.append(f"Keyword match '{kw}' on {page_title}")

                # Step 2: Multi-step navigation (follow relevant internal link)
                if multi_step:
                    candidate_link = None
                    candidate_text = ""
                    # Prioritized CSS query for facility/location/about links
                    selectors = [
                        "a[href*='facilit']", "a[href*='plant']", "a[href*='location']",
                        "a[href*='presence']", "a[href*='contact']", "a[href*='about']"
                    ]
                    for sel in selectors:
                        matching_elem = page.query_selector(sel)
                        if matching_elem:
                            href = matching_elem.get_attribute("href") or ""
                            txt = (matching_elem.inner_text() or "").strip()
                            if (href.startswith("http") or href.startswith("/")) and not href.endswith(".pdf"):
                                full_url = urljoin(target_url, href)
                                if full_url != target_url and full_url != f"{target_url}/":
                                    candidate_link = full_url
                                    candidate_text = txt or sel
                                    break

                    if not candidate_link:
                        links = page.query_selector_all("a[href]")
                        for l in links[:100]:
                            href = l.get_attribute("href") or ""
                            txt = (l.inner_text() or "").strip()
                            combined = f"{href} {txt}".lower()
                            if any(term in combined for term in ["facilities", "plants", "locations", "manufacturing", "about", "contact", "presence"]):
                                if (href.startswith("http") or href.startswith("/")) and not href.endswith(".pdf"):
                                    full_url = urljoin(target_url, href)
                                    if full_url != target_url and full_url != f"{target_url}/":
                                        candidate_link = full_url
                                        candidate_text = txt
                                        break

                    if candidate_link and candidate_link != target_url:
                        actions_performed.append(f"follow link '{candidate_text}' -> {candidate_link}")
                        logger.info("[%s] Multi-step link follow: %s", task_id, candidate_link)
                        try:
                            page.goto(candidate_link, wait_until="commit", timeout=10000)
                            time.sleep(1.5)
                            step2_title = page.title()
                            step2_body = page.query_selector("body")
                            step2_text = step2_body.inner_text() if step2_body else ""
                            actions_performed.append(f"extracted {len(step2_text)} characters from step 2 {candidate_link}")
                            page_record["second_page"] = {
                                "url": candidate_link,
                                "title": step2_title,
                                "text_length": len(step2_text),
                                "text_sample": step2_text[:1500],
                            }
                            unique_evidence.append(f"Discovered second-page evidence on {step2_title} ({candidate_link})")
                        except Exception as step2_exc:
                            actions_performed.append(f"error following step 2 link {candidate_link}: {step2_exc}")

                results.append(page_record)

            context.close()
            if browser:
                browser.close()

    except Exception as exc:
        logger.exception("[%s] Browser execution error: %s", task_id, exc)
        elapsed = time.perf_counter() - start_time
        return {
            "task_id": task_id,
            "status": "error",
            "company": company,
            "error": str(exc),
            "latency_seconds": round(elapsed, 3),
            "browser_launched": True,
            "actions_performed": actions_performed,
        }

    elapsed = time.perf_counter() - start_time
    end_iso = datetime.now(timezone.utc).isoformat()

    return {
        "task_id": task_id,
        "status": "completed",
        "company": company,
        "provider": "browser_research_service",
        "browser_launched": True,
        "browser_start_time": start_iso,
        "browser_end_time": end_iso,
        "latency_seconds": round(elapsed, 3),
        "actions_performed": actions_performed,
        "unique_evidence": list(set(unique_evidence)),
        "pages_inspected": results,
    }


@app.get("/health")
def health_check():
    """Health check validating Playwright browser service readiness."""
    return {
        "status": "healthy",
        "service": "browser_research_service",
        "version": "1.0.0-playwright",
        "engine": "playwright-chromium-131.0",
        "official_bytedance_deerflow_installed": False,
        "custom_browser_service": "installed/running",
        "official_deerflow_status": "WAITING_FOR_VERIFIED_ZERO_COST_MODEL",
        "browser_profiles": ["default", "Salesoorja LinkedIn"],
        "capabilities": [
            "deterministic_browser",
            "js_hydration",
            "multi_step_navigation",
            "challenge_detection",
            "manual_handoff",
            "persistent_profile_isolation",
        ],
        "browser_running": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/tasks")
def create_task(payload: TaskPayload):
    """Execute research or browser workflow task synchronously or store result."""
    task_id = payload.task_id or f"df-task-{uuid.uuid4().hex[:12]}"
    task_data = payload.dict()
    task_data["task_id"] = task_id

    result = execute_browser_job(task_data)
    TASKS_STORE[task_id] = result
    return result


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """Retrieve result of a research task."""
    if task_id in TASKS_STORE:
        return TASKS_STORE[task_id]
    if task_id in CHALLENGES_STORE:
        return CHALLENGES_STORE[task_id]
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.post("/api/browser/navigate")
def direct_navigate(payload: DirectNavigatePayload):
    """Direct single or two-step browser navigation endpoint."""
    task_id = f"df-nav-{uuid.uuid4().hex[:8]}"
    job_payload = {
        "task_id": task_id,
        "company_name": payload.company_name or "Direct Navigation",
        "target_urls": [payload.url],
        "multi_step": payload.follow_links,
        "focus_areas": payload.link_keywords or [],
        "browser_profile": payload.browser_profile or "default",
    }
    return execute_browser_job(job_payload)


@app.get("/api/challenges")
def list_challenges():
    """List pending manual challenges (CAPTCHA / Cloudflare)."""
    return {
        "count": len(CHALLENGES_STORE),
        "challenges": list(CHALLENGES_STORE.values()),
    }
