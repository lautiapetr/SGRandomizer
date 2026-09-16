# PyInstaller executes this file as Python; keep paths relative to the repository root.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
datas = collect_data_files("sgrand", includes=["configs/*.json", "gui/assets/*.svg"])

analysis = Analysis(
    [str(root / "packaging" / "gui_entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SGRand",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="SGRand",
)

if sys.platform == "darwin":
    application = BUNDLE(
        collection,
        name="SGRand.app",
        bundle_identifier="org.sgrand.randomizer",
        info_plist={
            "CFBundleDisplayName": "SGRand",
            "CFBundleShortVersionString": "0.7.0",
            "NSHighResolutionCapable": True,
        },
    )
