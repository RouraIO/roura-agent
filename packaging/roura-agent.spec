# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Roura Agent macOS app bundle.
Target: macOS 15+ (Tahoe), Apple Silicon (arm64)
"""

import sys
from pathlib import Path

# Ensure we're building for arm64
if sys.platform != 'darwin':
    raise RuntimeError("This spec is for macOS only")

block_cipher = None

# Project root
ROOT = Path(SPECPATH).parent

# Get version from constants.py
import importlib.util
constants_path = ROOT / 'roura_agent' / 'constants.py'
spec = importlib.util.spec_from_file_location('constants', constants_path)
constants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(constants)
VERSION = constants.VERSION

a = Analysis(
    [str(ROOT / 'packaging' / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include any data files needed at runtime
        (str(ROOT / 'roura_agent'), 'roura_agent'),
    ],
    hiddenimports=[
        'roura_agent',
        'roura_agent.cli',
        'roura_agent.agent',
        'roura_agent.agent.loop',
        'roura_agent.tools',
        'roura_agent.tools.fs',
        'roura_agent.tools.git',
        'roura_agent.tools.shell',
        'roura_agent.tools.doctor',
        'roura_agent.tools.github',
        'roura_agent.tools.jira',
        'roura_agent.tools.project',
        'roura_agent.tools.review',
        'roura_agent.tools.glob',
        'roura_agent.llm',
        'roura_agent.llm.ollama',
        'roura_agent.llm.openai',
        'roura_agent.llm.anthropic',
        'typer',
        'typer.main',
        'click',
        'rich',
        'rich.console',
        'rich.panel',
        'rich.table',
        'rich.progress',
        'rich.prompt',
        'rich.markdown',
        'rich._unicode_data',
        'rich._unicode_data.unicode17-0-0',
        'rich._unicode_data.unicode16-0-0',
        'rich._unicode_data.unicode15-1-0',
        'rich._unicode_data.unicode15-0-0',
        'rich._unicode_data.unicode14-0-0',
        'rich._unicode_data.unicode13-0-0',
        'httpx',
        'pydantic',
        'dotenv',
        'prompt_toolkit',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='roura-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX not recommended on macOS
    console=True,  # CLI app needs console
    disable_windowed_traceback=False,
    argv_emulation=True,  # Required for macOS .app
    target_arch='arm64',
    codesign_identity=None,  # Signing handled separately
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='roura-agent',
)

app = BUNDLE(
    coll,
    name='Roura Agent.app',
    icon=None,  # TODO: Add icon path when available
    bundle_identifier='io.roura.agent',
    info_plist={
        'CFBundleName': 'Roura Agent',
        'CFBundleDisplayName': 'Roura Agent',
        'CFBundleIdentifier': 'io.roura.agent',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'CFBundleExecutable': 'roura-agent',
        'CFBundlePackageType': 'APPL',
        'LSMinimumSystemVersion': '15.0',
        'LSArchitecturePriority': ['arm64'],
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSEnvironment': {
            'LANG': 'en_US.UTF-8',
        },
    },
)
