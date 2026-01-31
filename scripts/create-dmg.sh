#!/bin/bash
set -euo pipefail

# Roura Agent DMG Creation Script
# Creates a drag-to-Applications DMG installer

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"

# Get version from constants.py if not set
if [[ -z "${VERSION:-}" ]]; then
    VERSION=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from roura_agent.constants import VERSION; print(VERSION)" 2>/dev/null || echo "0.0.0")
fi

APP_NAME="Roura Agent"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_NAME="Roura-Agent-${VERSION}.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
DMG_TEMP="$DIST_DIR/dmg-temp"

echo "=== Creating DMG Installer ==="
echo "Version: $VERSION"
echo "App:     $APP_PATH"
echo "Output:  $DMG_PATH"
echo ""

# Check app exists
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: App bundle not found at $APP_PATH"
    echo "Run ./scripts/build-macos.sh first"
    exit 1
fi

# Check for create-dmg or use hdiutil fallback
USE_CREATE_DMG=false
if command -v create-dmg &> /dev/null; then
    USE_CREATE_DMG=true
    echo "Using create-dmg for pretty installer"
else
    echo "create-dmg not found, using hdiutil (basic DMG)"
    echo "Install create-dmg for prettier installer: brew install create-dmg"
fi

# Clean previous
rm -f "$DMG_PATH"
rm -rf "$DMG_TEMP"

if $USE_CREATE_DMG; then
    # Create DMG with create-dmg (prettier)
    create-dmg \
        --volname "$APP_NAME $VERSION" \
        --volicon "$APP_PATH/Contents/Resources/AppIcon.icns" 2>/dev/null || true \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 100 \
        --icon "$APP_NAME.app" 150 190 \
        --hide-extension "$APP_NAME.app" \
        --app-drop-link 450 190 \
        --no-internet-enable \
        "$DMG_PATH" \
        "$APP_PATH"
else
    # Fallback: Create DMG with hdiutil
    echo "Creating staging directory..."
    mkdir -p "$DMG_TEMP"

    # Copy app
    cp -R "$APP_PATH" "$DMG_TEMP/"

    # Create Applications symlink
    ln -s /Applications "$DMG_TEMP/Applications"

    # Create DMG
    echo "Creating DMG..."
    hdiutil create \
        -volname "$APP_NAME $VERSION" \
        -srcfolder "$DMG_TEMP" \
        -ov \
        -format UDZO \
        "$DMG_PATH"

    # Cleanup
    rm -rf "$DMG_TEMP"
fi

# Verify DMG
echo ""
echo "=== Verifying DMG ==="

echo -n "Checking DMG exists... "
if [[ -f "$DMG_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

echo -n "Checking DMG mounts... "
# Extract mount point - handle paths with spaces by getting everything after the volume ID
MOUNT_POINT=$(hdiutil attach "$DMG_PATH" -nobrowse | grep "/Volumes" | sed 's/.*\(\/Volumes.*\)/\1/')
if [[ -d "$MOUNT_POINT" ]]; then
    echo "PASS ($MOUNT_POINT)"

    echo -n "Checking app in DMG... "
    if [[ -d "$MOUNT_POINT/$APP_NAME.app" ]]; then
        echo "PASS"
    else
        echo "FAIL"
        hdiutil detach "$MOUNT_POINT" -quiet
        exit 1
    fi

    echo -n "Checking Applications symlink... "
    if [[ -L "$MOUNT_POINT/Applications" ]]; then
        echo "PASS"
    else
        echo "WARN (no symlink)"
    fi

    hdiutil detach "$MOUNT_POINT" -quiet
else
    echo "FAIL (could not mount)"
    exit 1
fi

echo ""
echo "=== DMG Created ==="
echo "File: $DMG_PATH"
echo "Size: $(du -sh "$DMG_PATH" | cut -f1)"
echo ""
echo "To install: Open DMG and drag '$APP_NAME' to Applications"
