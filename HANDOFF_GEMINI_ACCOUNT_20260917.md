# SALESOORJA GEMINI ACCOUNT HANDOFF
**Date:** 2026-09-17  
**Purpose:** Complete context transfer to new Gemini IDE account. This file supersedes all session memory.

---

## Repository

```
REPO_PATH:         C:\Users\HP\OneDrive\Desktop\Projects\New-try-01
ACTIVE_WORKTREE:   C:\Users\HP\OneDrive\Desktop\Projects\New-try-01
BRANCH:            feature/ai-sales-intelligence-modules-8-17
```

---

## Production

```
PRODUCTION_HEAD:   0188715d87a642297fc9e7857e3bd9dca7853065
PRODUCTION_SHORT:  0188715
PRODUCTION_STATUS: RUNNING 24×7 — DO NOT TOUCH
PRODUCTION_BRANCH: feature/llm-followup-information-gain
```

Production is the commit at `0188715`. It runs autonomously 24×7 via Celery + the `SalesoorjaOperator`. **Never deploy, reset, or restart production without explicit user authorization.**

---

## Development

```
DEV_BRANCH:        feature/ai-sales-intelligence-modules-8-17
DEV_WORKTREE:      C:\Users\HP\OneDrive\Desktop\Projects\New-try-01
PHASE2_COMMIT:     f3e5e72d04e347a1af2004a49257179820decd99  (f3e5e72)
CHECKPOINT_TAG:    salesoorja-phase2-account-handoff-final-20260917
```

Phase 2 is **committed but NOT deployed**. Production remains at `0188715`.

---

## Completed Phase 2 Work

### 1. `PersonEnrichmentEligibilityGate`
**File:** `backend/services/person_enrichment_eligibility_gate.py`  
**Wired into:** `backend/services/decision_maker_discovery.py` (replaces `is_apollo_eligible_lead()` call at line ~1607)

**What it does:**  
Replaces the hardcoded `APOLLO_ELIGIBLE_THRESHOLD = 0.85` as the sole Apollo enrichment gate with a structured 3-tier decision:

```
tier 1 — HARD BLOCKS (deterministic, no LLM):
  - trigger invalid
  - facility linkage not DIRECT/STRONG
  - ICP score < 85
  - composite score < 0.60 (HARD_FLOOR)
  - current_employment not VERIFIED
  - facility_relationship not in {DIRECT, STRONG, FACILITY_OWNER, FACILITY_FUNCTION_OWNER, GROUP_FUNCTION_OWNER}

tier 2 — DETERMINISTIC PASS (no LLM):
  - score >= 0.85 AND authority in APOLLO_AUTHORITY_CLASSES → PASS

tier 2b — GRACE WINDOW (no LLM, risk-flagged):
  - score in [0.80, 0.85) AND authority in APOLLO_AUTHORITY_CLASSES → PASS with borderline_score_grace_window flag
  ← This is the key unlock for Aarti Pharmalabs / TASL at score ~84

tier 3 — LLM REVIEW (borderline [0.60, 0.80)):
  - DeepSeek primary / Gemini fallback
  - LLM says YES → enrich_contact=True
  - LLM unavailable → fallback to deterministic block
```

**APOLLO_AUTHORITY_CLASSES** (eligible for grace window + deterministic pass):
- `DIRECT_CALIBRATION_OWNER`
- `METROLOGY_OWNER`
- `STRONG_PLANT_QUALITY_OWNER`
- `FACILITY_OWNER`
- `GROUP_FUNCTION_OWNER`

**Returns:** `EnrichmentEligibilityDecision` dataclass with:
- `enrich_contact: bool`
- `authority_confidence: HIGH | MEDIUM | LOW | BLOCKED`
- `reason: str`
- `commercial_relevance: DIRECT | STRONG | WEAK | NONE`
- `risk_flags: List[str]`
- `evidence_used: List[str]`
- `llm_used: bool`

---

### 2. `ContactWaterfallService`
**File:** `backend/services/contact_waterfall_service.py`  
**Status:** Implemented, importable, tested. **NOT yet called from the live operator path** — it exists as a service module. The existing `run_contact_fallback_ladder()` in `person_intelligence_service.py` still handles the waterfall in the DMD pipeline. Wiring `ContactWaterfallService` as the authoritative path is a Phase 2.1 task.

**What it does:**  
Multi-candidate Apollo enrichment waterfall (max 3 per account):

```
For each candidate (up to 3):
  1. PersonEnrichmentEligibilityGate.evaluate() → if blocked → skip (no Apollo credit)
  2. enrich_fn(candidate) → Apollo call
  3. classify_email_verification_level() → VERIFIED_PROVIDER | VERIFIED_PUBLIC_SOURCE |
                                           DOMAIN_VALID_PATTERN_ONLY | EXTRAPOLATED | UNKNOWN
  4. is_send_ready_email() → only VERIFIED_PROVIDER or VERIFIED_PUBLIC_SOURCE → send-ready
  5. If not send-ready → continue to next candidate
  6. If send-ready → return CONTACT_FOUND immediately
Exhausted all candidates → HOLD_CONTACT_NOT_FOUND
```

**Hard policy: `MX_ONLY_SEND_ALLOWED = False`**  
Domain existence (MX record present, email pattern derived) NEVER upgrades an email to send-ready.

---

### 3. `SalesPersonalizationV2Engine`
**File:** `backend/services/sales_personalization_v2.py`  
**Wired into:** `backend/services/salesoorja_operator.py` (V2 runs first; V1 `SalesPersonalizationPipeline` is automatic fallback)

**What it does:**  
Persona-first, zero-invention deterministic email generation:

- **6 persona value angles** keyed by authority class: `METROLOGY_OWNER`, `DIRECT_CALIBRATION_OWNER`, `STRONG_PLANT_QUALITY_OWNER`, `FACILITY_OWNER`, `GROUP_FUNCTION_OWNER`, `PROCUREMENT`
- **Capability selection:** 1–3 groups matching company industry (no full-list dumping)
- **Word count target:** 90–130 words (body only, excl. signature)
- **Natural openers:** 5 rotation templates — no "I read about..." repetition
- **CTA:** Consultative, low-friction ("brief exchange at your convenience")
- **Signature:** Fixed NABL / CC-3963 block

**`classify_claim(text)` → `(label, violation_description)`**
- `EXPLICIT_EVIDENCE` — grounded in record
- `SAFE_GENERIC` — contains qualifying hedge (typically, usually, may, can)
- `UNSUPPORTED_SPECIFIC` — FORBIDDEN (triggers `CLAIM_VIOLATION` result)

**`FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS`** (regex blocks):
- `Your NDT equipment...` type claims
- Specific process/equipment inference without evidence
- `48/72/24-hour turnaround` SLA claims
- `free audit / free calibration / free trial`
- Unapproved regional center names (Pune & Dahej Regional Centers)

**V1 fallback:** If V2 returns `CLAIM_VIOLATION` or `quality_score < 85`, operator automatically falls back to `SalesPersonalizationPipeline` (LLM-based).

---

### 4. `decision_maker_discovery.py` Integration
**File:** `backend/services/decision_maker_discovery.py` lines ~1607–1640

`is_apollo_eligible_lead()` call at that location is **replaced** with `PersonEnrichmentEligibilityGate.evaluate()`. The gate is lazy-loaded via `get_enrichment_eligibility_gate()` singleton.

Logging added: `[ENRICHMENT_GATE] Candidate: X | Eligible: Y | Confidence: Z | Reason: ...`

---

### 5. `salesoorja_operator.py` Integration
**File:** `backend/services/salesoorja_operator.py`

Two changes:
1. **`__init__`**: Added `self._personalization_v2 = SalesPersonalizationV2Engine()` alongside existing `self._personalization`
2. **`_process_production_account`**: V2 engine tried first; if `VALIDATED` and `quality_score >= 85` → used; else falls back to V1
3. **`_select_send_candidate`**: Extended gate:
   - Facility relationship set expanded: `{FACILITY_OWNER, FACILITY_FUNCTION_OWNER, GROUP_FUNCTION_OWNER, DIRECT, STRONG}`
   - Score gate: `>= 0.85` OR (`>= 0.80` AND authority in `APOLLO_AUTHORITY_CLASSES`)
   - Logging: `[SELECT_CANDIDATE]` with grace window flag

---

### 6. Phase 2 Tests
**File:** `backend/tests/test_funnel_recovery_phase2.py`

```
29 tests — 29 PASSED, 0 FAILED (16.89s)

TestPersonEnrichmentEligibilityGate  (12 tests)
TestContactWaterfallService          (7 tests)
TestSalesPersonalizationV2Engine     (7 tests)
TestOperatorSelectSendCandidatePhase2 (3 tests)
```

---

## Business Problem Being Solved

**Current measured funnel (at time of audit):**
```
RESEARCHED:          43 accounts
TRIGGER_PASS:         6
FACILITY_PASS:        5
QUALIFIED:            5
PERSON_FOUND:         5
EMPLOYMENT_VERIFIED:  5
CONTACT_ENRICHMENT:  ~2 Apollo calls
EMAIL_FOUND:          2
EMAIL_USABLE:         1
SEND_READY:           0
SENT_TODAY:           0
```

**Target commercial outcome:**
```
DISCOVERY → QUALIFIED → RIGHT PERSON → VERIFIED EMAIL → GOOD PERSONALIZATION
→ SEND_READY → SENT → REPLY → ENQUIRY → SALES OPPORTUNITY
```

**Business goal through Sep 20:** Maximize genuine enquiries. Do not optimize technical metrics in isolation.

The primary downstream bottleneck identified: verified email + send-ready path. Phase 2 addresses this by unlocking borderline-score high-authority candidates (score 80–84 with verified employment + direct facility link) that were previously blocked by the hardcoded 0.85 cutoff.

---

## LLM-FIRST PRINCIPLE

**Use LLM for:**
- Semantic trigger interpretation
- Facility/location reasoning
- Person authority and commercial relevance assessment
- Research strategy selection
- Personalization generation
- Next-best action decisions

**Use deterministic code for:**
- Zero-invention claim enforcement
- Duplicate send suppression (14-day window)
- Opt-out / bounce protection
- Daily send caps
- DB integrity and atomic concurrency
- Exact evidence grounding checks

**Do NOT replace semantic judgment with arbitrary hard thresholds.**  
The original 0.85 hard cutoff was the problem Phase 2 solves.

---

## Full Regression Result (2026-09-17)

```
TOTAL_COLLECTED:  846 tests
PASSED:           845
FAILED:           1
SKIPPED:          0
DURATION:         318.30s (5m 18s)

FAILED TEST:
  tests/test_evidence_deep_dive.py::test_adaptive_research_generates_targeted_queries
  AttributeError: 'AdaptiveResearchService' object has no attribute '_generate_targeted_queries'
  
CAUSE: Pre-existing stale test (confirmed by git stash + retest on prior commit).
       The test calls a private method that was renamed/removed in a previous session.
       This failure is NOT caused by Phase 2 changes.
       
ACTION: Do not fix this test as part of Phase 2. It is a separate pre-existing regression.
```

---

## Known Issues and Caveats

1. **Phase 2 NOT deployed.** Production at `0188715`. Do not deploy without explicit user authorization.

2. **`ContactWaterfallService` is not yet wired into the live operator path.** It is implemented and tested as a module but `_process_production_account` in the operator still uses `run_contact_fallback_ladder()` from `person_intelligence_service.py` via the DMD pipeline. Wiring `ContactWaterfallService` as the authoritative path is the key Phase 2.1 task.

3. **Upstream 43→5 audit counts were inconsistent** across earlier reports. Do NOT change trigger gates based on approximate taxonomy counts until a single authoritative account list is reconciled from the database. Audit scripts exist in `backend/scripts/` for this purpose.

4. **CONTACT_ENRICHMENT_INVOKED discrepancy:** Earlier reports showed 2 vs 3 Apollo calls. Authoritative count: **2 unique Apollo enrichment attempts; 1 dedup skip** (deduplication within 30-day window).

5. **14-day duplicate recipient protection must not be relaxed.** This is a hard commercial policy.

6. **No fabricated emails.** Never promote MX-only or pattern-extrapolated emails to send-ready.

7. **No unsupported specific claims.** `classify_claim()` must be run on all outreach body text before release.

8. **Pre-existing regression:** `test_evidence_deep_dive.py::test_adaptive_research_generates_targeted_queries` fails due to stale private method reference. Fix separately, not as part of Phase 2.

---

## Next Task: Phase 2.1 — Validation and Deployment Readiness

Do NOT auto-deploy when the new account starts. Complete these steps first:

1. **Verify ContactWaterfallService is actually called** in the real operator production path (not just importable). Wire it if not.
2. **Verify PersonEnrichmentEligibilityGate replaces the old 0.85 sole gate** in the actual DMD call path — read the live code at `decision_maker_discovery.py` line ~1607 to confirm.
3. **Verify PersonalizationV2 is used** by the normal operator flow — confirm `_personalization_v2.generate_outreach()` is invoked before `_personalization.personalize_record()`.
4. **Reconcile all 43 researched accounts** into mutually exclusive funnel categories using the scripts in `backend/scripts/`.
5. **Harden claim grounding** for person responsibilities and equipment-specific claims (check `sales_personalization_v2.py::FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS` coverage).
6. **Dry-run today's 5 qualified accounts** through the integrated Phase 2 path.
7. **Run focused Phase 2 tests + full regression** — both must pass.
8. Only then evaluate whether Phase 2 is safe to deploy.

---

## Audit Scripts Available

These scripts are in `backend/scripts/` and committed in the handoff checkpoint:

- `audit_all_43_companies.py` — Full 43-account funnel audit with LLM second-look on trigger failures
- `audit_signals_and_opportunities.py` — Signal and opportunity gate audit
- `check_apollo_enrichment_timestamps.py` — Apollo enrichment dedup and timestamp check
- `reconcile_and_audit_today.py` — Today's complete revenue funnel from PostgreSQL + runtime state
- `run_upstream_43_audit_and_latency.py` — Stage latency and upstream loss taxonomy

---

## Resume Commands (Safe Read-Only)

```powershell
# Open repository
cd C:\Users\HP\OneDrive\Desktop\Projects\New-try-01

# Verify working branch and HEAD
git branch --show-current
git rev-parse HEAD
git rev-parse --short HEAD

# Fetch all remote state and tags
git fetch --all --tags

# Verify worktrees
git worktree list

# Verify checkpoint tag
git tag -l "salesoorja-phase2*"
git show salesoorja-phase2-account-handoff-final-20260917 --stat

# Verify Phase 2 commit content
git show --stat f3e5e72

# Verify production head separately (in production worktree)
git -C "C:\Users\HP\OneDrive\Desktop\Projects\New-try-01-dev-task3d1f" rev-parse HEAD

# Verify production Docker containers (read-only)
docker ps --filter "name=salesoorja"

# Run ONLY Phase 2 focused tests (safe, no production I/O)
cd backend
python -m pytest tests/test_funnel_recovery_phase2.py -v
```

---

## Files To Read Before Changing Anything

Read in this exact order:

1. `HANDOFF_GEMINI_ACCOUNT_20260917.md` — this file (already reading)
2. `backend/services/person_enrichment_eligibility_gate.py` — full gate implementation
3. `backend/services/decision_maker_discovery.py` lines 1600–1660 — gate call site
4. `backend/services/salesoorja_operator.py` lines 125–160 (constructor), 1630–1680 (personalization), 1755–1800 (candidate selection)
5. `backend/services/contact_waterfall_service.py` — waterfall service
6. `backend/services/sales_personalization_v2.py` — V2 engine + claim guard
7. `backend/tests/test_funnel_recovery_phase2.py` — full Phase 2 test suite
8. `backend/services/person_intelligence_service.py` lines 2039–2086 — current `run_contact_fallback_ladder()` (what ContactWaterfallService will replace)
9. `backend/services/decision_maker_discovery.py` full function `discover_and_rank_decision_makers` — understand the full pipeline before changing anything

---

## Important Commit History

```
f3e5e72  feat(funnel): Phase 2 — PersonEnrichmentEligibilityGate, ContactWaterfallService, PersonalizationV2   ← DEV HEAD
0188715  fix(research): harden distributed followup reservation lifecycle                                       ← PRODUCTION HEAD
f386da3  fix(research): harden followup memory migration and concurrency
414c457  feat(research): add llm information-gain gate for follow-up searches
68ad737  feat(entity): reconcile operating entity granularity...
```

---

## Constraints That Must Never Be Violated

- **No fabricated emails** (no MX-only promotion, no pattern extrapolation to send-ready)
- **No unsupported specific claims** in outreach (no NDT-specific inference, no fabricated SLAs)
- **No 14-day duplicate suppression bypass**
- **No deployment without explicit user "deploy" authorization**
- **No changes to the production operator state file or Celery workers**
- **No lowering of truth gates to increase send volume**
- **No manual approval steps added to the pipeline** (must remain autonomous)
- **Postgres is the durable source of truth for followup query memory** (Redis is cache only)
