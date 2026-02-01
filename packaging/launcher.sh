#!/bin/bash
# Roura Agent Terminal Launcher
# This script launches Roura Agent in a new Terminal window

# Get the directory containing this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_BINARY="$SCRIPT_DIR/roura-agent"

# Check if running from .app bundle
if [[ "$SCRIPT_DIR" == *".app/Contents/MacOS"* ]]; then
    APP_BINARY="$SCRIPT_DIR/roura-agent"
fi

# Launch in a new Terminal window using osascript
osascript <<EOF
tell application "Terminal"
    activate
    do script "clear && '$APP_BINARY' && exit"
end tell
EOF
