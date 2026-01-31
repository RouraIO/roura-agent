#!/bin/bash
set -euo pipefail

# Roura Agent Release Script
# Creates a new release with version sync across:
# - pyproject.toml
# - roura_agent/constants.py
# - Git tag
# - GitHub release (triggers PyPI publish)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <version> [--draft] [--prerelease]"
    echo ""
    echo "Arguments:"
    echo "  version      Version to release (e.g., 2.0.1, 2.1.0)"
    echo ""
    echo "Options:"
    echo "  --draft      Create as draft release"
    echo "  --prerelease Mark as pre-release"
    echo "  --dry-run    Show what would be done without making changes"
    echo ""
    echo "Examples:"
    echo "  $0 2.0.1                    # Release v2.0.1"
    echo "  $0 2.1.0-beta.1 --prerelease # Pre-release"
    echo "  $0 2.0.1 --dry-run          # Preview changes"
    exit 1
}

# Parse arguments
VERSION=""
DRAFT=""
PRERELEASE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --draft)
            DRAFT="--draft"
            shift
            ;;
        --prerelease)
            PRERELEASE="--prerelease"
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            if [[ -z "$VERSION" ]]; then
                VERSION="$1"
            else
                echo -e "${RED}Unknown argument: $1${NC}"
                usage
            fi
            shift
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    echo -e "${RED}Error: Version is required${NC}"
    usage
fi

# Validate version format
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
    echo -e "${RED}Error: Invalid version format. Use semver (e.g., 2.0.1, 2.1.0-beta.1)${NC}"
    exit 1
fi

# Extract version parts
MAJOR=$(echo "$VERSION" | cut -d. -f1)
MINOR=$(echo "$VERSION" | cut -d. -f2)
PATCH=$(echo "$VERSION" | cut -d. -f3 | cut -d- -f1)

cd "$PROJECT_ROOT"

echo "=== Roura Agent Release Script ==="
echo "Version: v$VERSION"
echo ""

# Check for uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "${RED}Error: Uncommitted changes detected. Commit or stash them first.${NC}"
    git status --short
    exit 1
fi

# Check we're on main branch
BRANCH=$(git branch --show-current)
if [[ "$BRANCH" != "main" ]]; then
    echo -e "${YELLOW}Warning: Not on main branch (currently on: $BRANCH)${NC}"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Get current version
CURRENT_VERSION=$(grep -m1 'version = ' pyproject.toml | sed 's/.*"\(.*\)".*/\1/')
echo "Current version: $CURRENT_VERSION"
echo "New version: $VERSION"
echo ""

if $DRY_RUN; then
    echo -e "${YELLOW}=== DRY RUN - No changes will be made ===${NC}"
    echo ""
fi

# Step 1: Update version in pyproject.toml
echo "1. Updating pyproject.toml..."
if ! $DRY_RUN; then
    sed -i '' "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
fi
echo -e "${GREEN}   ✓ pyproject.toml${NC}"

# Step 2: Update version in constants.py
echo "2. Updating roura_agent/constants.py..."
if ! $DRY_RUN; then
    sed -i '' "s/^VERSION = \".*\"/VERSION = \"$VERSION\"/" roura_agent/constants.py
    sed -i '' "s/^VERSION_TUPLE = (.*)/VERSION_TUPLE = ($MAJOR, $MINOR, $PATCH)/" roura_agent/constants.py
fi
echo -e "${GREEN}   ✓ roura_agent/constants.py${NC}"

# Step 3: Run tests
echo "3. Running tests..."
if ! $DRY_RUN; then
    if ! pytest tests/ -q --tb=no > /dev/null 2>&1; then
        echo -e "${RED}   ✗ Tests failed! Aborting release.${NC}"
        git checkout -- pyproject.toml roura_agent/constants.py
        exit 1
    fi
fi
echo -e "${GREEN}   ✓ All tests pass${NC}"

# Step 4: Commit version bump
echo "4. Committing version bump..."
if ! $DRY_RUN; then
    git add pyproject.toml roura_agent/constants.py
    git commit -m "chore: bump version to $VERSION"
fi
echo -e "${GREEN}   ✓ Committed${NC}"

# Step 5: Create git tag
echo "5. Creating git tag v$VERSION..."
if ! $DRY_RUN; then
    git tag -a "v$VERSION" -m "Release v$VERSION"
fi
echo -e "${GREEN}   ✓ Tagged${NC}"

# Step 6: Push to origin
echo "6. Pushing to origin..."
if ! $DRY_RUN; then
    git push origin main
    git push origin "v$VERSION"
fi
echo -e "${GREEN}   ✓ Pushed${NC}"

# Step 7: Create GitHub release (triggers PyPI publish)
echo "7. Creating GitHub release..."
if ! $DRY_RUN; then
    # Generate release notes from git log
    PREV_TAG=$(git describe --tags --abbrev=0 "v$VERSION^" 2>/dev/null || echo "")
    if [[ -n "$PREV_TAG" ]]; then
        NOTES=$(git log --pretty=format:"- %s" "$PREV_TAG..v$VERSION" | head -20)
    else
        NOTES="Initial release"
    fi

    gh release create "v$VERSION" \
        --title "v$VERSION" \
        --notes "$NOTES" \
        $DRAFT \
        $PRERELEASE
fi
echo -e "${GREEN}   ✓ GitHub release created${NC}"

echo ""
echo -e "${GREEN}=== Release v$VERSION complete! ===${NC}"
echo ""
echo "The GitHub release will trigger PyPI publishing automatically."
echo "Monitor at: https://github.com/RouraIO/roura-agent/actions"
echo ""
echo "PyPI package: https://pypi.org/project/roura-agent/"
