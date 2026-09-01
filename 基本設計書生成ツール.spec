# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPECPATH).resolve()
PLUGIN_ROOT = ROOT / "plugins" / "personal" / "standard_word_generator"

datas = [
    (str(ROOT / "基本設計書generator.html"), "."),
    (str(PLUGIN_ROOT / "templates"), "plugins/personal/standard_word_generator/templates"),
    (str(ROOT / "local_backend" / "data"), "local_backend/data"),
    (str(ROOT / "local_backend" / "templates"), "local_backend/templates"),
]
binaries = []
hiddenimports = []

# python-docx depends on lxml's compiled extensions and package data.  They are
# reached through the plugin directory added to sys.path at runtime, so make
# both distributions explicit instead of relying on Analysis to discover them.
for package in ("docx", "lxml"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports

# Uvicorn selects protocols/loops dynamically, python-multipart exposes both
# import names, and Pydantic/Pillow load implementation modules at runtime.
for package in (
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "pydantic_core",
    "multipart",
    "python_multipart",
    "PIL",
    "webview",
):
    hiddenimports += collect_submodules(package)

# pywebview loads its GUI backend and bundled JavaScript at runtime.
webview_datas, webview_binaries, webview_imports = collect_all("webview")
datas += webview_datas
binaries += webview_binaries
hiddenimports += webview_imports

# The local backend intentionally imports this namespace package after adding
# PLUGIN_ROOT to sys.path.  Listing its runtime modules makes that dynamic
# import visible to PyInstaller without bundling the Dify-only tool entrypoints.
hiddenimports += [
    "tools.chapter_parser",
    "tools.docx_builder",
    "tools.paragraph_numbering",
    "tools.template_store",
]

a = Analysis(
    [str(ROOT / "run_local.py")], pathex=[str(ROOT), str(PLUGIN_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="基本設計書生成ツール", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=True, console=False)
