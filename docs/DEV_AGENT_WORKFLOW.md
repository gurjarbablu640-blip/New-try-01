# Salesoorja — Developer & Agent Workflow Guide
**GSD Planning + Antigravity Implementation + Ralph Bounded Execution + CodeRabbit Review**

---

## 1. Overview & Architecture Division of Responsibility

To avoid conflicting instructions or runaway loops, tools have distinct, non-overlapping responsibilities:

```
                  ┌───────────────────────────────┐
                  │          USER / IDE           │
                  │   Prompt & Requirement Spec   │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │         GSD ENGINE            │
                  │   Milestones, Slices, Plans   │
                  │   (.gsd/STATE.md, config.json)│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │       ANTIGRAVITY AGENT       │
                  │  Primary Coding & Architecture│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │       RALPH LOOP (OPTIONAL)   │
                  │   Bounded Iterative Stories   │
                  │   (Max 5 loops, Stop on error)│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │     TEST SUITE VERIFICATION   │
                  │  docker exec pytest (390 PASS)│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │       CODERABBIT REVIEW       │
                  │ Privacy-Guarded Diff Analysis │
                  │     (cr review --agent)       │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │     LOCAL GIT COMMIT          │
                  │   Clean, Verified Checkpoint  │
                  └───────────────────────────────┘
```

> [!IMPORTANT]
> **Cardinal Rule**: GSD and Ralph must NEVER independently control the same task simultaneously. GSD handles strategic decomposition and planning; Ralph handles isolated, bounded loop iteration on discrete test-backed user stories.

---

## 2. When to Use / When NOT to Use

### GSD (Get Shit Done)
- **When to USE**:
  - Planning complex architectural modules, large refactors, or new business epics.
  - Tracking milestone state (`.gsd/STATE.md`) and project memory.
  - Preparing acceptance criteria before touching code.
- **When NOT to USE**:
  - Trivial one-line bugfixes or typos.
  - Unattended autonomous execution without engineer review.

### Ralph Loop
- **When to USE**:
  - Multi-step, test-driven coding tasks where each step is small enough to fit in a single context window.
  - Repetitive refactorings validated by automated tests.
  - Tasks with clear stop conditions and zero side effects.
- **When NOT to USE**:
  - Open-ended, exploratory tasks with undefined acceptance criteria.
  - Anything touching real emails, live Apollo credits, or credentials.
  - Tasks requiring CAPTCHA solving or browser authentication.

### CodeRabbit
- **When to USE**:
  - Prior to creating git commits or opening pull requests.
  - Independent security, performance, and style audit of git diffs.
- **When NOT to USE**:
  - Mid-implementation when tests are still failing.
  - On branches containing unmasked secret files (handled automatically by `.coderabbit.yaml`).

---

## 3. Mandatory Salesoorja Production Safety Rules

Under all circumstances, agents and developers must adhere to these inviolable guardrails:

1. **NO Real Email Sending**:
   - `OUTBOUND_TEST_MODE` must remain `true` unless human user explicitly approves live production dispatch.
   - Prohibited from sending unsolicited emails to any external mailbox.
2. **NO Apollo Credit Consumption**:
   - Inactive/night mode must be respected (`APOLLO_ENABLED_FOR_LIVE_LOOKUP = False`).
   - Zero live Apollo calls unless subscription renewal is completed and authorized.
3. **NO Paid LLM Activation**:
   - `GEMINI_ACCOUNT_MODE` must remain `FREE_NO_BILLING`.
   - Paid models (e.g. paid OpenAI / Anthropic) must not be configured as silent fallback.
4. **NO Credential Printing**:
   - API keys, tokens, and passwords must never appear in logs, commit messages, or reports.
5. **NO CAPTCHA / Bot Evasion**:
   - Encountering login walls or CAPTCHAs must transition cleanly to `MANUAL_BROWSER_ACTION_REQUIRED`.
6. **NO Destructive Database Operations**:
   - Dropping tables, running `alembic downgrade base`, or running `TRUNCATE` is strictly forbidden.
7. **NO Force Pushes or Hard Resets**:
   - Never run `git push --force` or destructive `git reset --hard` on shared branches.
8. **Claim Hygiene**:
   - CC-3963 is Oorja Technical Services' lab accreditation certificate, never a customer standard.
   - Turnaround commitments (e.g. "48-hour turnaround") without verified commercial authorization are prohibited.

---

## 4. Local Command Cheat Sheet

### GSD Planning Engine
```bash
# View status and active milestone
python scripts/gsd/gsd.py status

# Inspect planning mode
python scripts/gsd/gsd.py plan

# Run test verification
python scripts/gsd/gsd.py verify
```

### Ralph Bounded Loop
```bash
# Check Ralph status and safe template
python scripts/ralph/ralph.py --status

# Windows PowerShell invocation
powershell -ExecutionPolicy Bypass -File scripts\ralph\ralph.ps1 -Status
```

### CodeRabbit Review
```bash
# Check version and doctor status
scripts\coderabbit\coderabbit.exe --version
scripts\coderabbit\coderabbit.exe doctor

# Check authentication
scripts\coderabbit\coderabbit.exe auth status

# One-time login (interactive browser action required)
scripts\coderabbit\coderabbit.exe auth login

# Run agent review
scripts\coderabbit\coderabbit.exe review --agent
```

### Test Suite Verification
```bash
docker exec -e PYTHONPATH=. salesoorja-backend pytest tests/ -q
```
