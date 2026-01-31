#!/bin/bash
set -euo pipefail

# Roura Agent Tarball Creation Script
# Creates a tarball suitable for Homebrew installation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"
VERSION="${VERSION:-1.7.0}"

APP_NAME="Roura Agent"
APP_PATH="$DIST_DIR/$APP_NAME.app"
TARBALL_NAME="roura-agent_${VERSION}_macos_arm64.tar.gz"
TARBALL_PATH="$DIST_DIR/$TARBALL_NAME"
TARBALL_TEMP="$DIST_DIR/tarball-temp"

echo "=== Creating Tarball for Homebrew ==="
echo "Version: $VERSION"
echo "App:     $APP_PATH"
echo "Output:  $TARBALL_PATH"
echo ""

# Check app exists
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: App bundle not found at $APP_PATH"
    echo "Run ./scripts/build-macos.sh first"
    exit 1
fi

# Clean previous
rm -f "$TARBALL_PATH"
rm -rf "$TARBALL_TEMP"

# Create staging directory
echo "Creating staging directory..."
mkdir -p "$TARBALL_TEMP/roura-agent"

# Copy the CLI binary (not the whole .app for Homebrew)
# Homebrew users want just the binary
BINARY_PATH="$APP_PATH/Contents/MacOS/roura-agent"
if [[ ! -f "$BINARY_PATH" ]]; then
    echo "ERROR: Binary not found at $BINARY_PATH"
    exit 1
fi

# For Homebrew, we need the binary and its dylibs
# Copy the entire MacOS directory contents
cp -R "$APP_PATH/Contents/MacOS/"* "$TARBALL_TEMP/roura-agent/"

# Also copy Frameworks and Resources if they exist
if [[ -d "$APP_PATH/Contents/Frameworks" ]]; then
    cp -R "$APP_PATH/Contents/Frameworks" "$TARBALL_TEMP/roura-agent/"
fi

if [[ -d "$APP_PATH/Contents/Resources" ]]; then
    # Only copy necessary resources, not the whole thing
    mkdir -p "$TARBALL_TEMP/roura-agent/Resources"
    # Copy base.lproj if exists
    if [[ -d "$APP_PATH/Contents/Resources/base.lproj" ]]; then
        cp -R "$APP_PATH/Contents/Resources/base.lproj" "$TARBALL_TEMP/roura-agent/Resources/"
    fi
fi

# Create tarball
echo "Creating tarball..."
cd "$TARBALL_TEMP"
tar -czf "$TARBALL_PATH" roura-agent

# Cleanup
rm -rf "$TARBALL_TEMP"

# Verify tarball
echo ""
echo "=== Verifying Tarball ==="

echo -n "Checking tarball exists... "
if [[ -f "$TARBALL_PATH" ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

echo -n "Checking tarball contents... "
if tar -tzf "$TARBALL_PATH" | grep -q "roura-agent/roura-agent"; then
    echo "PASS"
else
    echo "FAIL (binary not found in tarball)"
    tar -tzf "$TARBALL_PATH"
    exit 1
fi

# Calculate SHA256 for Homebrew formula
SHA256=$(shasum -a 256 "$TARBALL_PATH" | cut -d' ' -f1)

echo ""
echo "=== Tarball Created ==="
echo "File:   $TARBALL_PATH"
echo "Size:   $(du -sh "$TARBALL_PATH" | cut -f1)"
echo "SHA256: $SHA256"
echo ""
echo "Use this SHA256 in the Homebrew formula"
