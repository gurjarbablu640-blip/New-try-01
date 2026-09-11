---
name: gsd
description: "GSD (Get Shit Done) spec-driven planning and context engineering engine. Use when planning new milestones, breaking features into slices and tasks, or checking project phase state in Salesoorja. Triggers on: /gsd, gsd plan, gsd status, spec driven development."
user-invocable: true
---

# GSD (Get Shit Done) - Salesoorja Planning Engine

GSD provides structured spec-driven development, milestone planning, and context engineering.

## When to Use GSD
- Decomposing new business features into structured milestones and slices.
- Generating clear acceptance criteria and verification plans.
- Maintaining project memory and state across development sessions.

## When NOT to Use GSD
- Quick bugfixes, one-line edits, or simple syntax repairs.
- Direct autonomous execution without user approval.
- Performing destructive database or deployment operations.

## Available Local Commands
```bash
# Check current project milestone and slice status
python scripts/gsd/gsd.py status
# Or on Windows PowerShell:
.\scripts\gsd\gsd.ps1 -Status

# Inspect or generate spec-driven plans
python scripts/gsd/gsd.py plan

# Run project verification tests
python scripts/gsd/gsd.py verify
```

## Project Configuration & State
- State file: `.gsd/STATE.md`
- Configuration: `.gsd/config.json`
- Milestones directory: `.gsd/milestones/`
