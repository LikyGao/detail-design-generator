# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")
a = Analysis(
    ["run_local.py"], pathex=[], binaries=webview_binaries,
    datas=[("基本設計書generator.html", ".")] + webview_datas,
    hiddenimports=webview_hiddenimports, hookspath=[], runtime_hooks=[],
    excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="基本設計書生成ツール",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False,
)
