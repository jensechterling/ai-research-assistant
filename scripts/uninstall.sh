#!/bin/bash
set -e

echo "Uninstalling ai-research-assistant..."

# Unload launchd job
launchctl unload ~/Library/LaunchAgents/com.claude.ai-research-assistant.plist 2>/dev/null || true

# Remove plist
rm -f ~/Library/LaunchAgents/com.claude.ai-research-assistant.plist

# Optionally remove wake schedule
read -p "Remove wake schedule? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo pmset repeat cancel
    echo "Wake schedule removed"
fi

echo "Uninstalled"
