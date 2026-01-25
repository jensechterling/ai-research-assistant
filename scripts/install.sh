#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing ai-research-assistant..."

# Create directories
mkdir -p ~/.claude/logs
mkdir -p "$PROJECT_DIR/data"
mkdir -p "$PROJECT_DIR/exports"

# Make scripts executable
chmod +x "$PROJECT_DIR/scripts/run.sh"
chmod +x "$PROJECT_DIR/scripts/uninstall.sh"

# Copy launchd plist
cp "$PROJECT_DIR/templates/com.claude.ai-research-assistant.plist" ~/Library/LaunchAgents/

# Load the job
launchctl load ~/Library/LaunchAgents/com.claude.ai-research-assistant.plist

# Set wake schedule (requires sudo)
echo "Setting wake schedule..."
sudo pmset repeat wake MTWRFSU 05:55:00

echo ""
echo "Installed successfully!"
echo ""
echo "  Pipeline will run daily at 6:00 AM"
echo "  Machine will wake at 5:55 AM"
echo ""
echo "  Manual run:   cd $PROJECT_DIR && uv run ai-research-assistant run"
echo "  Check status: cd $PROJECT_DIR && uv run ai-research-assistant status"
echo "  View logs:    tail -f ~/.claude/logs/ai-research-assistant.log"
