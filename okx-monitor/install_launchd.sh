#!/bin/zsh
set -euo pipefail

BOT_DIR="/Users/jinxu/.openclaw/workspace】/okx-monitor"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LABEL="com.jinxu.okx-monitor.live"

mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$BOT_DIR/$LABEL.plist" "$LAUNCH_AGENTS_DIR/$LABEL.plist"

launchctl bootout gui/$(id -u) "$LAUNCH_AGENTS_DIR/$LABEL.plist" >/dev/null 2>&1 || true
launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS_DIR/$LABEL.plist"
launchctl enable gui/$(id -u)/$LABEL

launchctl print gui/$(id -u)/$LABEL | head -n 30 || true

echo "Done. Live crypto card will push every 30 minutes."
