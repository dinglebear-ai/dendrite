#!/usr/bin/env bash
# Point this repository's hooks at the tracked ones in scripts/hooks.
# Run once per clone: scripts/install-hooks.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath scripts/hooks
printf 'core.hooksPath -> scripts/hooks\n'
printf 'installed: %s\n' "$(ls scripts/hooks | tr '\n' ' ')"
