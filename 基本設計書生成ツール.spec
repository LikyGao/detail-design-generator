# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("uvicorn")
a = Analysis(
    ["run_local.py"], pathex=[],
    binaries=[],
    datas=[
        ("基本設計書generator.html", "."),
        ("plugins/personal/standard_word_generator/tools", "plugins/personal/standard_word_generator/tools"),
        ("plugins/personal/standard_word_generator/templates", "plugins/personal/standard_word_generator/templates"),
        ("local_backend/data", "local_backend/data"),
        ("local_backend/templates", "local_backend/templates"),
    ],
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="基本設計書生成ツール", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True, console=True)
