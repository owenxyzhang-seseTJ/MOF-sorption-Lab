# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_dir = Path.cwd()
icon_path = project_dir / "static" / "mof-sorption-lab-icon.ico"
version_info_path = project_dir / "windows" / "version_info.txt"

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("MANUAL.md", "."),
]

hiddenimports = [
    "waitress",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "openpyxl",
    "pyiast",
    "pygaps",
    "CoolProp",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MOF Sorption Lab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(icon_path) if icon_path.exists() else None,
    version=str(version_info_path) if version_info_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MOF Sorption Lab",
)
