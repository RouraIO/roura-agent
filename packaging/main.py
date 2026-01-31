#!/usr/bin/env python3
"""
Entry point for PyInstaller-built Roura Agent.
This script properly imports and runs the CLI from the package.
"""
import sys
import os

# Ensure the package is importable
if hasattr(sys, '_MEIPASS'):
    # Running from PyInstaller bundle
    sys.path.insert(0, sys._MEIPASS)

from roura_agent.cli import app

if __name__ == "__main__":
    app()
