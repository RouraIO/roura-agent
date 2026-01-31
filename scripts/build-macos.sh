#!/bin/bash
set -euo pipefail

# Roura Agent macOS Build Script
# Builds .app bundle using PyInstaller for arm64

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/dist"

# Get version from constants.py if not set
if [[ -z "${VERSION:-}" ]]; then
    VERSION=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from roura_agent.constants import VERSION; print(VERSION)" 2>/dev/null || echo "0.0.0")
fi

echo "=== Roura Agent macOS Build ==="
echo "Version: $VERSION"
echo "Project: $PROJECT_ROOT"
echo "Output:  $BUILD_DIR"
echo ""

# Check we're on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script must run on macOS"
    exit 1
fi

# Check architecture
ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" ]]; then
    echo "WARNING: Building on $ARCH, target is arm64"
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PYTHON_VERSION"

# Create/activate venv for clean build
VENV_DIR="$PROJECT_ROOT/.build-venv"
echo ""
echo "=== Setting up build environment ==="

if [[ -d "$VENV_DIR" ]]; then
    echo "Removing old build venv..."
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip wheel setuptools > /dev/null
pip install pyinstaller > /dev/null
pip install -e "$PROJECT_ROOT" > /dev/null

# Clean previous builds
echo ""
echo "=== Cleaning previous builds ==="
rm -rf "$BUILD_DIR"
rm -rf "$PROJECT_ROOT/build/roura-agent"

# Run PyInstaller
echo ""
echo "=== Running PyInstaller ==="
cd "$PROJECT_ROOT"
pyinstaller \
    --distpath "$BUILD_DIR" \
    --workpath "$PROJECT_ROOT/build/pyinstaller-work" \
    --clean \
    --noconfirm \
    "$PROJECT_ROOT/packaging/roura-agent.spec"

# Verify .app was created
APP_PATH="$BUILD_DIR/Roura Agent.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: .app bundle not created"
    exit 1
fi

echo ""
echo "=== Smoke Tests ==="

# Test 1: App exists and has correct structure
echo -n "Checking .app structure... "
if [[ -f "$APP_PATH/Contents/MacOS/roura-agent" ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi

# Test 2: Binary is arm64
echo -n "Checking architecture... "
BINARY_ARCH=$(file "$APP_PATH/Contents/MacOS/roura-agent" | grep -o "arm64" || true)
if [[ "$BINARY_ARCH" == "arm64" ]]; then
    echo "PASS (arm64)"
else
    # May be universal or x86_64 on CI
    echo "WARN (not arm64, got: $(file "$APP_PATH/Contents/MacOS/roura-agent"))"
fi

# Test 3: CLI runs
echo -n "Checking CLI execution... "
if "$APP_PATH/Contents/MacOS/roura-agent" --version &> /dev/null; then
    VERSION_OUTPUT=$("$APP_PATH/Contents/MacOS/roura-agent" --version 2>&1)
    echo "PASS ($VERSION_OUTPUT)"
else
    echo "FAIL"
    exit 1
fi

# Test 4: Doctor command works
echo -n "Checking doctor command... "
if "$APP_PATH/Contents/MacOS/roura-agent" doctor --json &> /dev/null; then
    echo "PASS"
else
    echo "WARN (doctor may have failed checks, but command ran)"
fi

# Cleanup build venv
deactivate
rm -rf "$VENV_DIR"

echo ""
echo "=== Build Complete ==="
echo "App bundle: $APP_PATH"
echo "Size: $(du -sh "$APP_PATH" | cut -f1)"
echo ""
echo "Next steps:"
echo "  ./scripts/create-dmg.sh      # Create DMG installer"
echo "  ./scripts/package-tarball.sh # Create tarball for Homebrew"
