#!/bin/bash
# launchd/cron entry point for the CRPC scheduler poller.
# Keeps a stable PATH (launchd runs with a minimal env) and logs run output.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

LOG="$DIR/logs/run.log"
mkdir -p "$DIR/logs"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') run start =====" >>"$LOG"
node "$DIR/poll.mjs" "$@" >>"$LOG" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') run end (exit $?) =====" >>"$LOG"
