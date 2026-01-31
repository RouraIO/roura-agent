#!/bin/bash
set -euo pipefail

# Roura Agent Secrets Scanner
# Scans build artifacts for accidentally included secrets
# Fails CI if secrets are found
# Compatible with bash 3.2+ (macOS default)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_ROOT/dist"

echo "=== Secrets Scanner ==="
echo ""

# Files/directories to scan
SCAN_TARGETS=()

# Add app bundle if exists
APP_PATH="$DIST_DIR/Roura Agent.app"
if [[ -d "$APP_PATH" ]]; then
    SCAN_TARGETS+=("$APP_PATH")
fi

# Add tarball if exists (extract to temp for scanning)
TARBALL=""
if [[ -d "$DIST_DIR" ]]; then
    TARBALL=$(find "$DIST_DIR" -name "*.tar.gz" 2>/dev/null | head -1 || true)
fi

TARBALL_TEMP=""
if [[ -n "$TARBALL" ]]; then
    TARBALL_TEMP="$DIST_DIR/tarball-scan-temp"
    rm -rf "$TARBALL_TEMP"
    mkdir -p "$TARBALL_TEMP"
    tar -xzf "$TARBALL" -C "$TARBALL_TEMP"
    SCAN_TARGETS+=("$TARBALL_TEMP")
fi

if [[ ${#SCAN_TARGETS[@]} -eq 0 ]]; then
    echo "No artifacts to scan. Run build first."
    echo "Scan skipped (no dist/ artifacts found)."
    exit 0
fi

echo "Scanning: ${SCAN_TARGETS[*]}"
echo ""

FOUND_SECRETS=false
FINDINGS_FILE=$(mktemp)

# Pattern names and regex pairs (bash 3.2 compatible)
PATTERN_NAMES=(
    "Environment file"
    "API Key variable"
    "Private key header"
    "AWS credentials"
    "GitHub token"
    "Generic secret"
    "Bearer token"
    "Basic auth"
    "Anthropic key"
    "OpenAI key"
    "Slack token"
    "Stripe key"
    "PyPI token"
)

PATTERNS=(
    '.env$|.env.local$|.env.production$'
    '_API_KEY=|_SECRET=|_TOKEN=|_PASSWORD='
    'BEGIN (RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY'
    'AKIA[0-9A-Z]{16}|aws_access_key_id|aws_secret_access_key'
    'ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}'
    'secret["\x27]?\s*[:=]\s*["\x27][^"\x27]{8,}'
    '[Bb]earer\s+[a-zA-Z0-9\-_\.]{20,}'
    '[Bb]asic\s+[A-Za-z0-9+/=]{20,}'
    'sk-ant-[a-zA-Z0-9\-]{20,}'
    'sk-[a-zA-Z0-9]{20,}'
    'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}'
    'sk_live_[0-9a-zA-Z]{24}|sk_test_[0-9a-zA-Z]{24}'
    'pypi-[A-Za-z0-9\-_]{50,}'
)

# Files/patterns to exclude (false positives)
EXCLUDE_PATTERNS=(
    "cacert.pem"           # SSL certs from certifi
    "secrets.py"           # Our own secrets detection module
    ".pyc"                 # Compiled Python
)

should_exclude() {
    local file="$1"
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        if [[ "$file" == *"$pattern"* ]]; then
            return 0  # true, should exclude
        fi
    done
    return 1  # false, should not exclude
}

# Function to scan a directory
scan_directory() {
    local dir="$1"
    local found=false
    local i=0

    while [[ $i -lt ${#PATTERNS[@]} ]]; do
        local pattern_name="${PATTERN_NAMES[$i]}"
        local pattern="${PATTERNS[$i]}"

        # Skip certain patterns in .py files (code references, not actual secrets)
        local exclude_py=false
        case "$pattern_name" in
            "Environment file"|"API Key variable"|"Private key header")
                exclude_py=true
                ;;
        esac

        # Search in file contents
        local matches
        matches=$(grep -rIl -E "$pattern" "$dir" 2>/dev/null || true)

        if [[ -n "$matches" ]]; then
            while IFS= read -r file; do
                # Skip excluded files
                if should_exclude "$file"; then
                    continue
                fi
                # Skip .py files for code-reference patterns
                if $exclude_py && [[ "$file" == *.py ]]; then
                    continue
                fi
                found=true
                echo "[$pattern_name] $file" >> "$FINDINGS_FILE"
            done <<< "$matches"
        fi

        i=$((i + 1))
    done

    # Check for suspicious file names (excluding known false positives)
    local suspicious_files
    suspicious_files=$(find "$dir" -type f \( \
        -name ".env" -o \
        -name ".env.*" -o \
        -name "*.pem" -o \
        -name "*.key" -o \
        -name "*.p12" -o \
        -name "*.pfx" -o \
        -name "credentials.json" -o \
        -name "service-account*.json" -o \
        -name "*.credentials" \
    \) 2>/dev/null | grep -v "cacert.pem" || true)

    if [[ -n "$suspicious_files" ]]; then
        while IFS= read -r file; do
            if ! should_exclude "$file"; then
                found=true
                echo "[Suspicious file] $file" >> "$FINDINGS_FILE"
            fi
        done <<< "$suspicious_files"
    fi

    echo "$found"
}

# Scan all targets
for target in "${SCAN_TARGETS[@]}"; do
    echo "Scanning: $target"
    result=$(scan_directory "$target")
    if [[ "$result" == "true" ]]; then
        FOUND_SECRETS=true
    fi
done

# Cleanup tarball temp
if [[ -n "$TARBALL_TEMP" ]] && [[ -d "$TARBALL_TEMP" ]]; then
    rm -rf "$TARBALL_TEMP"
fi

echo ""

# Report findings
if $FOUND_SECRETS; then
    echo "=== SECRETS FOUND - BUILD FAILED ==="
    echo ""
    echo "The following potential secrets were detected:"
    echo ""
    while IFS= read -r finding; do
        echo "  ❌ $finding"
    done < "$FINDINGS_FILE"
    echo ""
    echo "Please remove these files or values before releasing."
    echo ""
    echo "If these are false positives, review and update the patterns in:"
    echo "  scripts/scan-secrets.sh"
    rm -f "$FINDINGS_FILE"
    exit 1
else
    echo "=== No Secrets Found ==="
    echo "Scan passed. Safe to release."
    rm -f "$FINDINGS_FILE"
    exit 0
fi
