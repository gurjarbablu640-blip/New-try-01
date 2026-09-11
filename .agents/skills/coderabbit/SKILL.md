---
name: coderabbit
description: "CodeRabbit AI-powered code review and privacy-guarded quality inspection. Use before committing changes to run automated review and detect issues. Triggers on: /coderabbit, coderabbit review, review my changes, run code review."
user-invocable: true
---

# CodeRabbit - AI Code Review & Quality Guard

CodeRabbit provides automated, intelligent code reviews with privacy-guarded filtering.

## When to Run CodeRabbit
- After completing feature development and passing tests, before committing.
- When inspecting diffs for edge cases, performance issues, or security smells.
- Before opening pull requests.

## Privacy & Security Guardrails
- `.coderabbit.yaml` enforces exclusion of `.env*`, runtime credentials, tokens, and browser profiles.
- Does not review or transmit secrets.

## Commands
```bash
# Check version and doctor status
scripts\coderabbit\coderabbit.exe --version
scripts\coderabbit\coderabbit.exe doctor

# Check authentication status
scripts\coderabbit\coderabbit.exe auth status

# Review local changes (requires one-time auth login)
scripts\coderabbit\coderabbit.exe review --agent
```
