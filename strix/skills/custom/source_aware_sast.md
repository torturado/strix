---
name: source-aware-sast
description: Practical source-aware SAST and AST playbook for semgrep, ast-grep, gitleaks, and trivy fs
---

# Source-Aware SAST Playbook

Use this skill for source-heavy analysis where static and structural signals should guide dynamic testing.

## Fast Start

Run tools from repo root and store outputs in a dedicated artifact directory:

```bash
mkdir -p /workspace/.strix-source-aware
```

Before scanning, check shared wiki memory:

```text
1) list_notes(category="wiki")
2) get_note(note_id=...) for the selected repo wiki before analysis
3) Reuse matching repo wiki note if present
4) create_note(category="wiki") only if missing
```

After every major source-analysis batch, update the same repo wiki note with `update_note` so other agents can reuse your latest map.

## Baseline Coverage Bundle (Recommended)

Run this baseline once per repository before deep narrowing:

```bash
ART=/workspace/.strix-source-aware
mkdir -p "$ART"

semgrep scan --config p/default --config p/golang --config p/secrets \
  --metrics=off --json --output "$ART/semgrep.json" .
sg scan --json . > "$ART/ast-grep.json"
gitleaks detect --source . --report-format json --report-path "$ART/gitleaks.json" || true
trufflehog filesystem --no-update --json --no-verification . > "$ART/trufflehog.json" || true
trivy fs --format json --output "$ART/trivy-fs.json" .
```

If one tool is skipped or fails, record that in the shared wiki note along with the reason.

## Semgrep First Pass

Use Semgrep as the default static triage pass:

```bash
# Preferred deterministic profile set (works with --metrics=off)
semgrep scan --config p/default --config p/golang --config p/secrets \
  --metrics=off --json --output /workspace/.strix-source-aware/semgrep.json .

# If you choose auto config, do not combine it with --metrics=off
semgrep scan --config auto --json --output /workspace/.strix-source-aware/semgrep-auto.json .
```

If diff scope is active, restrict to changed files first, then expand only when needed.

## AST-Grep Structural Mapping

Use `sg` for structure-aware code hunting:

```bash
sg scan --json . > /workspace/.strix-source-aware/ast-grep.json
```

Target high-value patterns such as:
- missing auth checks near route handlers
- dynamic command/query construction
- unsafe deserialization or template execution paths
- file and path operations influenced by user input

## Tree-Sitter Assisted Repo Mapping

Use tree-sitter CLI for syntax-aware parsing when grep-level mapping is noisy:

```bash
tree-sitter parse -q <file>
```

Use outputs to improve route/symbol/sink maps for subsequent targeted scans.

## Secret and Supply Chain Coverage

Detect hardcoded credentials:

```bash
gitleaks detect --source . --report-format json --report-path /workspace/.strix-source-aware/gitleaks.json
trufflehog filesystem --json . > /workspace/.strix-source-aware/trufflehog.json
```

Run repository-wide dependency and config checks:

```bash
trivy fs --format json --output /workspace/.strix-source-aware/trivy-fs.json .
```

## Converting Static Signals Into Exploits

1. Rank candidates by impact and exploitability.
2. Trace source-to-sink flow for top candidates.
3. Build dynamic PoCs that reproduce the suspected issue.
4. Report only after dynamic validation succeeds.

## Wiki Update Template

Keep one wiki note per repository and update these sections:

```text
## Architecture
## Entrypoints
## AuthN/AuthZ
## High-Risk Sinks
## Static Findings Summary
## Dynamic Validation Follow-Ups
```

Before `agent_finish`, make one final `update_note` call to capture:
- scanner artifacts and paths
- top validated/invalidated hypotheses
- concrete dynamic follow-up tasks

## Anti-Patterns

- Do not treat scanner output as final truth.
- Do not spend full cycles on low-signal pattern matches.
- Do not report source-only findings without validation evidence.
- Do not create multiple wiki notes for the same repository when one already exists.
