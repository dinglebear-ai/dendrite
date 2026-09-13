#!/usr/bin/env bash
# Install the artifact server as a persistent macOS LaunchAgent.
# Run once: scripts/install-service.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

label=tv.tootie.artifacts
plist="$HOME/Library/LaunchAgents/$label.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/artifacts"
cp "scripts/launchd/$label.plist" "$plist"

launchctl unload "$plist" 2>/dev/null || true
launchctl load "$plist"

printf 'loaded %s\n' "$label"
printf 'listening on %s\n' "$(awk '/--host/{getline; print}' "$plist" | tr -d ' <>/string')"
printf 'logs: ~/Library/Logs/artifacts/server.{log,err}\n'
