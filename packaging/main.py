#!/usr/bin/env python3
"""
Entry point for PyInstaller-built Roura Agent.
This script properly imports and runs the CLI from the package.

If launched without a TTY (e.g., double-click), opens Terminal.app.
"""
import sys
import os
import subprocess


def is_interactive_terminal() -> bool:
    """Check if we're running in an interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def launch_in_terminal():
    """Launch this app in a new Terminal.app window."""
    # Get path to this executable
    if hasattr(sys, '_MEIPASS'):
        # Running from PyInstaller bundle
        exe_path = os.path.join(os.path.dirname(sys.executable), 'roura-agent')
    else:
        exe_path = sys.executable

    # Use osascript to open Terminal and run the CLI
    script = f'''
    tell application "Terminal"
        activate
        do script "clear && '{exe_path}' ; exit"
    end tell
    '''
    subprocess.run(['osascript', '-e', script], check=False)


def main():
    """Main entry point."""
    # Ensure the package is importable
    if hasattr(sys, '_MEIPASS'):
        sys.path.insert(0, sys._MEIPASS)

    # If not in a terminal (double-clicked), open Terminal.app
    if not is_interactive_terminal():
        launch_in_terminal()
        return

    # Running in terminal - start the CLI
    from roura_agent.cli import app
    app()


if __name__ == "__main__":
    main()
