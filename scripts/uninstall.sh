#!/bin/bash
set -euo pipefail

# Roura Agent Uninstaller
# Removes application and optionally user data
#
# Usage:
#   ./uninstall.sh              # Uninstall with prompts
#   ./uninstall.sh --dry-run    # Show what would be removed
#   ./uninstall.sh --force      # Uninstall without prompts
#   ./uninstall.sh --all        # Also remove user data

DRY_RUN=false
FORCE=false
REMOVE_DATA=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            ;;
        --force)
            FORCE=true
            ;;
        --all)
            REMOVE_DATA=true
            ;;
        --help|-h)
            echo "Roura Agent Uninstaller"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be removed without removing"
            echo "  --force      Skip confirmation prompts"
            echo "  --all        Also remove user data (config, cache, sessions)"
            echo "  --help       Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Use --help for usage"
            exit 1
            ;;
    esac
done

APP_NAME="Roura Agent"
APP_PATH="/Applications/$APP_NAME.app"
HOMEBREW_BINARY="/opt/homebrew/bin/roura-agent"
PIPX_BINARY="$HOME/.local/bin/roura-agent"

# User data locations
CONFIG_DIR="$HOME/.config/roura-agent"
CACHE_DIR="$HOME/.cache/roura-agent"
LOCAL_DATA_DIR="$HOME/.local/share/roura-agent"

echo "=== Roura Agent Uninstaller ==="
echo ""

if $DRY_RUN; then
    echo "DRY RUN MODE - No files will be removed"
    echo ""
fi

# Collect items to remove
ITEMS_TO_REMOVE=()
ITEMS_DESCRIPTION=()

# Check for app bundle
if [[ -d "$APP_PATH" ]]; then
    ITEMS_TO_REMOVE+=("$APP_PATH")
    ITEMS_DESCRIPTION+=("Application: $APP_PATH")
fi

# Check for Homebrew installation
if [[ -f "$HOMEBREW_BINARY" ]] || [[ -L "$HOMEBREW_BINARY" ]]; then
    ITEMS_TO_REMOVE+=("homebrew")
    ITEMS_DESCRIPTION+=("Homebrew: roura-agent (use 'brew uninstall roura-agent')")
fi

# Check for pipx installation
if [[ -f "$PIPX_BINARY" ]] || [[ -L "$PIPX_BINARY" ]]; then
    ITEMS_TO_REMOVE+=("pipx")
    ITEMS_DESCRIPTION+=("pipx: roura-agent (use 'pipx uninstall roura-agent')")
fi

# User data (if --all specified)
if $REMOVE_DATA; then
    if [[ -d "$CONFIG_DIR" ]]; then
        ITEMS_TO_REMOVE+=("$CONFIG_DIR")
        ITEMS_DESCRIPTION+=("Config: $CONFIG_DIR")
    fi
    if [[ -d "$CACHE_DIR" ]]; then
        ITEMS_TO_REMOVE+=("$CACHE_DIR")
        ITEMS_DESCRIPTION+=("Cache: $CACHE_DIR")
    fi
    if [[ -d "$LOCAL_DATA_DIR" ]]; then
        ITEMS_TO_REMOVE+=("$LOCAL_DATA_DIR")
        ITEMS_DESCRIPTION+=("Data: $LOCAL_DATA_DIR")
    fi
fi

# Show what will be removed
if [[ ${#ITEMS_TO_REMOVE[@]} -eq 0 ]]; then
    echo "Nothing to uninstall. Roura Agent is not installed."
    exit 0
fi

echo "The following will be removed:"
echo ""
for desc in "${ITEMS_DESCRIPTION[@]}"; do
    echo "  • $desc"
done
echo ""

if ! $REMOVE_DATA && [[ -d "$CONFIG_DIR" || -d "$CACHE_DIR" || -d "$LOCAL_DATA_DIR" ]]; then
    echo "Note: User data will be preserved. Use --all to remove:"
    [[ -d "$CONFIG_DIR" ]] && echo "  • $CONFIG_DIR"
    [[ -d "$CACHE_DIR" ]] && echo "  • $CACHE_DIR"
    [[ -d "$LOCAL_DATA_DIR" ]] && echo "  • $LOCAL_DATA_DIR"
    echo ""
fi

# Confirm unless --force or --dry-run
if ! $DRY_RUN && ! $FORCE; then
    read -p "Proceed with uninstall? [y/N] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
fi

# Perform uninstall
if $DRY_RUN; then
    echo "Would remove the items listed above."
    exit 0
fi

echo ""
echo "Uninstalling..."

for item in "${ITEMS_TO_REMOVE[@]}"; do
    case $item in
        homebrew)
            echo "  Uninstalling via Homebrew..."
            if command -v brew &> /dev/null; then
                brew uninstall roura-agent 2>/dev/null || echo "    (not installed via Homebrew)"
            fi
            ;;
        pipx)
            echo "  Uninstalling via pipx..."
            if command -v pipx &> /dev/null; then
                pipx uninstall roura-agent 2>/dev/null || echo "    (not installed via pipx)"
            fi
            ;;
        *)
            if [[ -e "$item" ]]; then
                echo "  Removing: $item"
                rm -rf "$item"
            fi
            ;;
    esac
done

echo ""
echo "=== Uninstall Complete ==="
echo ""
echo "Roura Agent has been removed."

if ! $REMOVE_DATA && [[ -d "$CONFIG_DIR" || -d "$CACHE_DIR" || -d "$LOCAL_DATA_DIR" ]]; then
    echo ""
    echo "User data was preserved. To remove it, run:"
    echo "  $0 --all"
fi
