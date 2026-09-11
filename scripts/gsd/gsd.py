#!/usr/bin/env python3
"""
GSD (Get Shit Done) - Local Project CLI & Spec-Driven Workflow Engine
Official source reference: open-gsd/gsd-pi (https://github.com/open-gsd/gsd-pi)
Workspace Scope: c:\\Users\\HP\\OneDrive\\Desktop\\Projects\\New-try-01
"""

import sys
import os
import json
import argparse
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
GSD_DIR = WORKSPACE_ROOT / ".gsd"
CONFIG_FILE = GSD_DIR / "config.json"
STATE_FILE = GSD_DIR / "STATE.md"

def ensure_gsd_initialized():
    GSD_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        default_config = {
            "name": "Salesoorja",
            "version": "1.0.0",
            "spec_format": "spec-driven-v2",
            "test_command": "docker exec -e PYTHONPATH=. salesoorja-backend pytest tests/ -q",
            "planning_dir": ".gsd",
            "milestones_dir": ".gsd/milestones",
            "safety_guards": {
                "prohibit_real_email": True,
                "prohibit_apollo_credits": True,
                "prohibit_paid_llm": True
            }
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
    
    if not STATE_FILE.exists():
        initial_state = """# GSD Project State: Salesoorja

## Current Status
- **Active Phase**: Tooling Integration & Guardrails
- **Current Milestone**: M0 - Workflow Setup (GSD, Ralph, CodeRabbit)
- **Active Slice**: S01 - Safe Tooling Configuration
- **Status**: READY (Non-autonomous planning mode)

## Architecture Baseline
- 390 / 390 Backend Tests PASS
- Gemini AI Primary (Free tier)
- Apollo Night Mode / Deferred Queue active
- Prohibited Actions: Real emails, Apollo live calls, paid LLMs
"""
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(initial_state)

def cmd_status(args):
    ensure_gsd_initialized()
    print("=== GSD Pi: Project Status ===")
    print(f"Workspace: {WORKSPACE_ROOT}")
    print(f"GSD Config: {CONFIG_FILE}")
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            print(f"Project: {cfg.get('name')} (v{cfg.get('version')})")
            print(f"Spec Format: {cfg.get('spec_format')}")
            print(f"Test Command: {cfg.get('test_command')}")
    if STATE_FILE.exists():
        print("\n--- Current State ---")
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("- **") or line.startswith("## "):
                    print(line.strip())
    print("\n[OK] GSD is initialized in project-local mode.")
    return 0

def cmd_plan(args):
    ensure_gsd_initialized()
    print("=== GSD Pi: Planning Engine ===")
    print("Planning mode: Context engineering and spec-driven breakdown.")
    print("To plan a new slice without modifying code, review .gsd/STATE.md and create milestones in .gsd/milestones/")
    return 0

def cmd_verify(args):
    ensure_gsd_initialized()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    test_cmd = cfg.get("test_command")
    print(f"=== GSD Pi: Verifying Project with '{test_cmd}' ===")
    ret = os.system(test_cmd)
    return ret

def main():
    parser = argparse.ArgumentParser(
        prog="gsd",
        description="GSD Pi - Local-first spec-driven development and context planning engine"
    )
    parser.add_argument("--version", action="version", version="GSD Pi 1.19.0 (Salesoorja project-local)")
    
    subparsers = parser.add_subparsers(dest="command", help="GSD commands")
    
    # status command
    sub_status = subparsers.add_parser("status", help="Show current project milestones and state")
    sub_status.set_defaults(func=cmd_status)
    
    # plan command
    sub_plan = subparsers.add_parser("plan", help="Inspect or generate spec-driven plans")
    sub_plan.set_defaults(func=cmd_plan)
    
    # verify command
    sub_verify = subparsers.add_parser("verify", help="Run configured verification test command")
    sub_verify.set_defaults(func=cmd_verify)
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
