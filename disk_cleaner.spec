# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for DISK / ADVANCED CLEANER TOOL (app.py)
# Build on Windows:   py -m PyInstaller --clean --noconfirm disk_cleaner.spec
# Output:             dist\Disk Cleaner.exe   (single file)
#
# This bundles the tricky web/desktop stack (FastHTML, uvicorn, starlette,
# pywebview + pythonnet) that PyInstaller can't fully auto-detect.

from PyInstaller.utils.hooks import collect_all

hiddenimports = [
    # uvicorn loads these dynamically at runtime:
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    # starlette form parsing + pywebview .NET bridge:
    "multipart", "clr",
]
datas, binaries = [], []

# Pull in everything (code + data files) for these packages.
for pkg in ("fasthtml", "fastcore", "fastlite", "starlette", "uvicorn",
            "webview", "clr_loader", "pythonnet", "anyio", "h11", "multipart"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print(f"[spec] skipping {pkg}: {exc}")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],   # not used by the web/desktop app; keeps size down
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Disk Cleaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX can trigger antivirus false positives; leave off
    runtime_tmpdir=None,
    console=False,           # no console window (set True temporarily to debug)
    disable_windowed_traceback=False,
    # icon="icon.ico",       # uncomment and drop an icon.ico next to this file
)
