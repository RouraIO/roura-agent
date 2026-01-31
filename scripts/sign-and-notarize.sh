#!/bin/bash
set -euo pipefail

# Roura Agent Code Signing and Notarization Script
# Signs and notarizes the .app and DMG for Gatekeeper approval
#
# Required environment variables for signing:
#   CODESIGN_IDENTITY  - "Developer ID Application: Your Name (TEAMID)"
#   APPLE_TEAM_ID      - Your 10-character Team ID
#
# Required environment variables for notarization (App Store Connect API):
#   ASC_KEY_ID         - App Store Connect API Key ID
#   ASC_ISSUER_ID      - App Store Connect Issuer ID
#   ASC_KEY_P8_BASE64  - Base64-encoded .p8 private key
#
# If any required variable is missing, the script will skip that step.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"

# Get version from constants.py if not set
if [[ -z "${VERSION:-}" ]]; then
    VERSION=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); from roura_agent.constants import VERSION; print(VERSION)" 2>/dev/null || echo "0.0.0")
fi

APP_NAME="Roura Agent"
APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/Roura-Agent-${VERSION}.dmg"

echo "=== Code Signing and Notarization ==="
echo "Version: $VERSION"
echo ""

# Check for signing identity
SIGNING_AVAILABLE=false
if [[ -n "${CODESIGN_IDENTITY:-}" ]] && [[ -n "${APPLE_TEAM_ID:-}" ]]; then
    SIGNING_AVAILABLE=true
    echo "Signing identity: $CODESIGN_IDENTITY"
    echo "Team ID: $APPLE_TEAM_ID"
else
    echo "SKIP: Signing credentials not configured"
    echo "  Set CODESIGN_IDENTITY and APPLE_TEAM_ID to enable signing"
fi

# Check for notarization credentials
NOTARIZE_AVAILABLE=false
if [[ -n "${ASC_KEY_ID:-}" ]] && [[ -n "${ASC_ISSUER_ID:-}" ]] && [[ -n "${ASC_KEY_P8_BASE64:-}" ]]; then
    NOTARIZE_AVAILABLE=true
    echo "Notarization: Configured (App Store Connect API)"
else
    echo "SKIP: Notarization credentials not configured"
    echo "  Set ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8_BASE64 to enable"
fi

echo ""

# Exit early if nothing to do
if ! $SIGNING_AVAILABLE; then
    echo "No signing credentials available. Exiting successfully."
    exit 0
fi

# Check app exists
if [[ ! -d "$APP_PATH" ]]; then
    echo "ERROR: App not found at $APP_PATH"
    exit 1
fi

# ===== SIGNING =====
echo "=== Signing App Bundle ==="

# Create entitlements file
ENTITLEMENTS_FILE="$DIST_DIR/entitlements.plist"
cat > "$ENTITLEMENTS_FILE" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    <key>com.apple.security.automation.apple-events</key>
    <true/>
</dict>
</plist>
EOF

echo "Signing with identity: $CODESIGN_IDENTITY"

# Sign all nested components first (deep signing)
find "$APP_PATH" -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) -print0 | while IFS= read -r -d '' file; do
    echo "  Signing: $(basename "$file")"
    codesign --force --options runtime \
        --entitlements "$ENTITLEMENTS_FILE" \
        --sign "$CODESIGN_IDENTITY" \
        --timestamp \
        "$file" 2>/dev/null || true
done

# Sign the main binary
echo "  Signing: roura-agent (main binary)"
codesign --force --options runtime \
    --entitlements "$ENTITLEMENTS_FILE" \
    --sign "$CODESIGN_IDENTITY" \
    --timestamp \
    "$APP_PATH/Contents/MacOS/roura-agent"

# Sign the entire app bundle
echo "  Signing: $APP_NAME.app (bundle)"
codesign --force --options runtime \
    --entitlements "$ENTITLEMENTS_FILE" \
    --sign "$CODESIGN_IDENTITY" \
    --timestamp \
    "$APP_PATH"

# Verify signature
echo ""
echo "Verifying signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
echo "Signature verification: PASS"

# Check with spctl (Gatekeeper)
echo ""
echo "Checking Gatekeeper assessment..."
if spctl --assess --type exec --verbose "$APP_PATH" 2>&1; then
    echo "Gatekeeper assessment: PASS"
else
    echo "Gatekeeper assessment: FAIL (expected before notarization)"
fi

# Clean up entitlements
rm -f "$ENTITLEMENTS_FILE"

# ===== NOTARIZATION =====
if ! $NOTARIZE_AVAILABLE; then
    echo ""
    echo "Skipping notarization (credentials not configured)"
    echo "App is signed but will show Gatekeeper warning"
    exit 0
fi

echo ""
echo "=== Notarizing App ==="

# Create API key file from base64
API_KEY_DIR="$HOME/.private_keys"
mkdir -p "$API_KEY_DIR"
API_KEY_FILE="$API_KEY_DIR/AuthKey_${ASC_KEY_ID}.p8"
echo "$ASC_KEY_P8_BASE64" | base64 --decode > "$API_KEY_FILE"

# Create ZIP for notarization
NOTARIZE_ZIP="$DIST_DIR/notarize-temp.zip"
echo "Creating ZIP for notarization..."
ditto -c -k --keepParent "$APP_PATH" "$NOTARIZE_ZIP"

# Submit for notarization
echo "Submitting to Apple notarization service..."
xcrun notarytool submit "$NOTARIZE_ZIP" \
    --key "$API_KEY_FILE" \
    --key-id "$ASC_KEY_ID" \
    --issuer "$ASC_ISSUER_ID" \
    --wait

# Clean up API key and ZIP
rm -f "$API_KEY_FILE"
rm -f "$NOTARIZE_ZIP"

# Staple notarization ticket
echo ""
echo "Stapling notarization ticket..."
xcrun stapler staple "$APP_PATH"

# Verify stapled signature
echo ""
echo "Verifying stapled app..."
spctl --assess --type exec --verbose "$APP_PATH"
echo "Notarization: COMPLETE"

# ===== RE-CREATE DMG WITH SIGNED APP =====
if [[ -f "$DMG_PATH" ]]; then
    echo ""
    echo "=== Re-creating DMG with signed app ==="

    # Remove old DMG
    rm -f "$DMG_PATH"

    # Re-run DMG creation
    "$SCRIPT_DIR/create-dmg.sh"

    # Sign DMG
    echo "Signing DMG..."
    codesign --force --sign "$CODESIGN_IDENTITY" --timestamp "$DMG_PATH"

    # Notarize DMG
    if $NOTARIZE_AVAILABLE; then
        echo "Notarizing DMG..."
        xcrun notarytool submit "$DMG_PATH" \
            --key "$API_KEY_FILE" \
            --key-id "$ASC_KEY_ID" \
            --issuer "$ASC_ISSUER_ID" \
            --wait

        xcrun stapler staple "$DMG_PATH"
        echo "DMG notarization: COMPLETE"
    fi
fi

echo ""
echo "=== Signing and Notarization Complete ==="
echo "App and DMG are ready for distribution"
