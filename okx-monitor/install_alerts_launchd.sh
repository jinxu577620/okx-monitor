#!/bin/zsh
set -euo pipefail

BOT_DIR="/Users/jinxu/.openclaw/workspace】/okx-monitor"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LIVE_LABEL="com.jinxu.okx-monitor.live"
ALERT_LABEL="com.jinxu.okx-monitor.alerts"

mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$BOT_DIR/$ALERT_LABEL.plist" "$LAUNCH_AGENTS_DIR/$ALERT_LABEL.plist"

launchctl bootout gui/$(id -u)/$LIVE_LABEL >/dev/null 2>&1 || true
launchctl disable gui/$(id -u)/$LIVE_LABEL >/dev/null 2>&1 || true

launchctl bootout gui/$(id -u) "$LAUNCH_AGENTS_DIR/$ALERT_LABEL.plist" >/dev/null 2>&1 || true
launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS_DIR/$ALERT_LABEL.plist"
launchctl enable gui/$(id -u)/$ALERT_LABEL

launchctl print gui/$(id -u)/$ALERT_LABEL | head -n 30 || true

echo "Done. Alert checks run every 15 minutes, but only push when signals appear."
