# GSD Project State: Salesoorja Overnight Autonomous Master Loop

## Current Status
- **Active Phase**: Phase 41-45 (Morning Freeze, Full Regression Suite & Autonomous Morning Report)
- **Current Milestone**: M1 - Overnight Master Loop: 150/day High-Quality Calibration Opportunity Production
- **Active Slice**: S07 - Morning Freeze Protocol & Comprehensive Final Audit
- **Status**: FROZEN_TESTS_PASSING_READY_FOR_REPORT
- **Hard Stop**: 2026-09-12 09:00:00 Asia/Kolkata
- **Freeze Time**: 2026-09-12 08:40:00 Asia/Kolkata (Triggered successfully at 08:05 IST)

## Objectives Progress
- [x] **A. Strict Trigger Recency Semantics & Regression Suite**: COMPLETE. Hardened 3-tier timing gate: 0–180d (CURRENT, PASS), 181–365d (RECENT, requires independent 2nd current ongoing source), >365d (STALE, fails timing unless explicit ongoing commercial evidence). 403 unit tests PASS.
- [x] **B. Forensic Re-Audit of Initial 5 Queue Records**: COMPLETE. Maruti Suzuki Atul Jain active P1 (44d CURRENT). Exide, Aarti, JSW, Dixon classified as `HOLD_STALE_TRIGGER` with complete timing reason and evidence history preserved.
- [x] **C. Autonomous Batches 25 through 13**: COMPLETE. Evaluated 734 unique accounts, 35 verified CURRENT leads queued.
- [x] **D. Autonomous Batch 14 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (153.92s, 1169.4 raw cos/hr). 1 verified CURRENT lead queued: Nilkamal Limited | Golam Rabbani (Operation Head, Sinnar Nashik plant, 1d old trigger).
- [x] **E. Autonomous Batch 15 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (379.91s, 473.8 raw cos/hr). 5 verified CURRENT leads queued: Veljan Denison, Indo National, PCBL, Hikal, FDC.
- [x] **F. Autonomous Batch 16 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (273.53s, 658.1 raw cos/hr). 3 verified CURRENT leads queued: KCP Limited, RACL Geartech Limited, Bilcare Limited.
- [x] **G. Autonomous Batch 17 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (291.18s, 618.2 raw cos/hr). 4 verified CURRENT leads queued: Rana Sugars Limited, Archidply Industries Limited, Pokarna Limited, Tanfac Industries Limited.
- [x] **H. Autonomous Batch 18 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (273.63s, 657.8 raw cos/hr). 3 verified CURRENT leads queued: Kopran Limited, McNally Bharat Engineering, Syncom Formulations.
- [x] **I. Autonomous Batch 19 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (168.38s, 1069.0 raw cos/hr). 2 valid triggers discovered, 0 qualified (failed multi-unit facility linkage).
- [x] **J. Autonomous Batch 20 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (181.58s, 991.3 raw cos/hr). 4 valid triggers discovered, 0 qualified (failed facility linkage).
- [x] **K. Autonomous Batch 21 (50 Accounts)**: COMPLETE. Evaluated 50 brand-new accounts (169.41s, 1062.5 raw cos/hr). 5 valid triggers discovered, 0 qualified (failed facility linkage).
- [x] **L. Overall Overnight Volume**: COMPLETE. **1,134 Unique Indian Industrial Manufacturing Accounts Evaluated**.
- [x] **M. Failure Funnel Tracking**: COMPLETE. Complete funnel tracking across all 1,134 evaluated accounts (NO_TRIGGER, STALE_TRIGGER, RECENT_NO_ONGOING_EVIDENCE, WRONG_ENTITY, FACILITY_UNKNOWN, TRIGGER_FACILITY_WEAK, NO_PERSON, FUNCTION_UNKNOWN).
- [x] **N. Apollo Queue Truth**: COMPLETE. Exactly 51 active records in `apollo_pending_queue.json`, 100% CURRENT (<= 180 days old). Exactly 0 stale triggers in active queue. Exactly 4 held stale records safely quarantined. Zero Apollo live credits consumed.
- [x] **O. Morning Freeze Protocol**: COMPLETE. Ceased new research, executed 403 test regressions (100% PASS), audited queue truth (0 violations), executed clean local git commit.
- [x] **P. Authoritative Morning Report**: COMPLETED before 09:00 IST.

## Architecture & Operational Baseline
- Starting Baseline Tests: 390 / 390 PASS
- Intermediate Regression Tests: 403 / 403 PASS
- Final Freeze Test Suite: **403 / 403 PASS** (0 failures, 12 warnings, runtime: 42.40s)
- Total Accounts Evaluated: 1,134 Unique Indian Industrial Accounts
- Total Verified Active Leads in Queue: 51 Leads (100% CURRENT, <= 180d)
- Total Quarantined Stale Leads: 4 Leads (`HOLD_STALE_TRIGGER`)
- Active Queue Stale Violations: 0
- LLM: Gemini Primary (`gemini-3.1-flash-lite`, 50 RPM safety ceiling, 0 paid calls, automatic candidate fallback)
- Search: SearXNG with `bing news` + `reuters` + `bing` with `safe_search: 1`
- Browser Escalation: Custom Playwright Chromium service (`salesoorja-deerflow:8001`) verified operational
- Apollo Mode: Night Mode / Deferred Queue (0 live calls, 0 credits consumed, status: `PENDING_APOLLO_RENEWAL`)
- Email Mode: `OUTBOUND_TEST_MODE = True` (0 real emails sent, previews only)
- LinkedIn: Public snippet / search discovery only (0 authwall bypass attempts, 0 creds entered)
- Safety: Zero force pushes, zero destructive DB operations, zero secret leaks, zero git pushes (local commits only)
