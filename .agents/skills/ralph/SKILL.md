---
name: ralph
description: "Ralph Loop bounded iterative execution system. Use for bounded, test-driven coding loops on clearly defined PRD items with strict safety stop conditions. Triggers on: /ralph, ralph loop, run ralph, bounded agent loop."
user-invocable: true
---

# Ralph Loop - Bounded Iterative Coding Engine

Ralph executes discrete, test-driven user stories in clean, bounded iterations until completion or safety stoppage.

## When to Use Ralph
- Executing well-defined, multi-step user stories with automated tests.
- Iterative feature work where each step has verifiable acceptance criteria.
- Bounded refactoring where test suites validate correctness.

## When NOT to Use Ralph
- Open-ended, exploratory, or architectural research tasks.
- Tasks involving real email dispatch, Apollo credit consumption, or paid APIs.
- Tasks that require manual browser interactions (e.g. CAPTCHA, LinkedIn authentication).

## Safety Rules (Enforced)
- **Max Iterations**: Hard limit of 5-10 iterations.
- **Stop Condition**: Stops immediately upon test failure, error, or completion.
- **Prohibited**: NO real emails, NO Apollo calls, NO paid LLM fallbacks, NO `git reset --hard`, NO database drops.

## Commands
```bash
# Check status without running
python scripts/ralph/ralph.py --status
# Or in PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\ralph\ralph.ps1 -Status

# Inspect safe bounded template:
# scripts/ralph/salesoorja_safe_template.json
```
