#!/bin/zsh
set -euo pipefail

BOT_DIR="/Users/jinxu/.openclaw/workspace】/maco-news-bot"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
MORNING_LABEL="com.jinxu.maco-news.morning"
EVENING_LABEL="com.jinxu.maco-news.evening"

mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$BOT_DIR/$MORNING_LABEL.plist" "$LAUNCH_AGENTS_DIR/$MORNING_LABEL.plist"
cp "$BOT_DIR/$EVENING_LABEL.plist" "$LAUNCH_AGENTS_DIR/$EVENING_LABEL.plist"

launchctl bootout gui/$(id -u) "$LAUNCH_AGENTS_DIR/$MORNING_LABEL.plist" >/dev/null 2>&1 || true
launchctl bootout gui/$(id -u) "$LAUNCH_AGENTS_DIR/$EVENING_LABEL.plist" >/dev/null 2>&1 || true

launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS_DIR/$MORNING_LABEL.plist"
launchctl bootstrap gui/$(id -u) "$LAUNCH_AGENTS_DIR/$EVENING_LABEL.plist"

launchctl enable gui/$(id -u)/$MORNING_LABEL
launchctl enable gui/$(id -u)/$EVENING_LABEL

echo "Installed LaunchAgents:"
launchctl print gui/$(id -u)/$MORNING_LABEL | head -n 20 || true
launchctl print gui/$(id -u)/$EVENING_LABEL | head -n 20 || true

echo "Done. Morning report at 08:00, evening report at 20:00."
