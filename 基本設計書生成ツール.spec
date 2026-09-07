# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

repo_root = Path(SPECPATH)
plugin_root = repo_root / "plugins" / "personal" / "standard_word_generator"
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

a = Analysis(
    ["run_local.py"],
    pathex=[str(plugin_root)],
    binaries=webview_binaries,
    datas=[
        ("基本設計書generator.html", "."),
        ("local_backend/local_bridge.js", "local_backend"),
        ("local_backend/template_manager_patch.js", "local_backend"),
    ] + webview_datas,
    hiddenimports=webview_hiddenimports + [
        "tools.chapter_parser",
        "tools.template_store",
        "tools.docx_builder",
        "tools.paragraph_numbering",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="基本設計書生成ツール",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
