#!/usr/bin/env python3
"""
Ralph Loop - Cross-platform Bounded CLI Runner
"""
import sys
import os
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PS1_SCRIPT = SCRIPT_DIR / "ralph.ps1"

def main():
    args = sys.argv[1:]
    ps_args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1_SCRIPT)]
    # map python style --flags to PS style -flags
    for a in args:
        if a.startswith("--"):
            ps_args.append("-" + a[2:].capitalize())
        else:
            ps_args.append(a)
    ret = subprocess.run(ps_args)
    return ret.returncode

if __name__ == "__main__":
    sys.exit(main())
