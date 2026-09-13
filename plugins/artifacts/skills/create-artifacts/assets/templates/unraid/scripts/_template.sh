#!/usr/bin/env bash
# [One line: what this harness proves. This comment becomes the artifact's
#  description in the index, so make it a claim, not a label.]
#
# Read-only: greps source and (optionally) runs real production code paths.
# Never mutates the target repository.
set -euo pipefail

core_repo=/Users/jmagar/workspace/core
# plugins_repo=/Users/jmagar/workspace/unraid-elixir-plugins

pass(){ printf 'PASS  %s\n' "$1"; }
fail(){ printf 'FAIL  %s\n' "$1"; exit 1; }
require_text(){ rg -q "$1" "$2" || fail "$3"; pass "$3"; }
require_absent(){ rg -q "$1" "$2" && fail "$3"; pass "$3"; }

cd "$core_repo"

printf '[HARNESS NAME] — REPRODUCIBLE EVIDENCE\n'
printf 'target: %s\n' "$(git rev-parse HEAD)"
printf 'worktree: %s\n\n' "$(git status --porcelain | wc -l | tr -d ' ') modified files"

# --- Claim 1: [state the claim exactly as the report states it] --------------
require_text 'pattern' 'lib/unraid/[path].ex' 'claim 1 — [what a PASS proves]'

# --- Claim 2: [state the claim] ----------------------------------------------
require_absent 'pattern' 'lib/unraid/[path].ex' 'claim 2 — [what a PASS proves]'

# --- Claim 3: measured behavior ----------------------------------------------
# Prefer running the real module over asserting on source text. When you must
# assert on text, say so in the report's .limit block: grep proves a code path
# exists, not that it executes.

printf '\nALL CLAIMS PASSED\n'
printf 'Boundary: [what a full PASS does NOT prove — mirror the report .limit blocks]\n'
