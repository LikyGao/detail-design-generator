"""Windows-native file dialogs for desktop HTTP actions.

The localhost FastAPI routes run on worker threads. Calling
``pywebview.Window.create_file_dialog`` from those threads can deadlock WebView2's
GUI message loop on real Windows desktops.  The classic Win32 common dialogs run
on the calling worker thread and therefore keep pywebview's UI thread untouched.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
from ctypes import wintypes
from pathlib import Path

from .desktop import DesktopApi, WINDOW_TITLE
from .services.staging import (
    read_project_archive,
    remove_staged_file,
    stage_bytes,
    staged_path,
)


# OPENFILENAME flags used by the classic common dialog API.
OFN_OVERWRITEPROMPT = 0x00000002
OFN_PATHMUSTEXIST = 0x00000800
OFN_FILEMUSTEXIST = 0x00001000
OFN_EXPLORER = 0x00080000
OFN_NOCHANGEDIR = 0x00000008


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def _owner_hwnd():
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowW.restype = wintypes.HWND
    return user32.FindWindowW(None, WINDOW_TITLE) or None


def _filter_text(file_kind: str) -> str:
    if file_kind == "word":
        return "Word Document (*.docx)\0*.docx\0All files (*.*)\0*.*\0\0"
    return "DDG Project (*.ddgproj)\0*.ddgproj\0All files (*.*)\0*.*\0\0"


def _win32_dialog(*, save: bool, suggested_name: str = "", file_kind: str) -> Path | None:
    if os.name != "nt":
        raise OSError("Windows native dialog is only available on Windows")

    max_chars = 32768
    buffer = ctypes.create_unicode_buffer(max_chars)
    if suggested_name:
        buffer.value = str(Path(suggested_name).name)[: max_chars - 1]

    default_ext = "docx" if file_kind == "word" else "ddgproj"
    title = "Word ファイルの保存先を選択" if file_kind == "word" else (
        "案件ファイルの保存先を選択" if save else "案件ファイルを開く"
    )

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = _owner_hwnd()
    ofn.lpstrFilter = _filter_text(file_kind)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    ofn.nMaxFile = max_chars
    ofn.lpstrTitle = title
    ofn.lpstrDefExt = default_ext
    ofn.Flags = OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR
    if save:
        ofn.Flags |= OFN_OVERWRITEPROMPT
    else:
        ofn.Flags |= OFN_FILEMUSTEXIST

    comdlg32 = ctypes.windll.comdlg32
    fn = comdlg32.GetSaveFileNameW if save else comdlg32.GetOpenFileNameW
    fn.argtypes = (ctypes.POINTER(OPENFILENAMEW),)
    fn.restype = wintypes.BOOL

    if fn(ctypes.byref(ofn)):
        return Path(buffer.value)

    comdlg32.CommDlgExtendedError.restype = wintypes.DWORD
    error = int(comdlg32.CommDlgExtendedError())
    if error == 0:
        return None  # user cancelled
    raise OSError(f"Windows common dialog failed: 0x{error:04X}")


def _fallback_pywebview_dialog(self: DesktopApi, *, save: bool, suggested_name: str, file_kind: str):
    """Compatibility fallback for non-Windows source development only."""
    import webview

    if self.main_window is None:
        return None
    dialog_type = self._dialog_type(webview, "SAVE" if save else "OPEN")
    if save:
        result = self.main_window.create_file_dialog(
            dialog_type,
            save_filename=suggested_name,
            file_types=(
                "Word Document (*.docx)" if file_kind == "word" else "DDG Project (*.ddgproj)",
                "All files (*.*)",
            ),
        )
    else:
        result = self.main_window.create_file_dialog(
            dialog_type,
            allow_multiple=False,
            file_types=("DDG Project (*.ddgproj)", "All files (*.*)"),
        )
    return self._first_dialog_path(result)


def _choose_path(self: DesktopApi, *, save: bool, suggested_name: str = "", file_kind: str):
    if os.name == "nt":
        return _win32_dialog(save=save, suggested_name=suggested_name, file_kind=file_kind)
    return _fallback_pywebview_dialog(
        self, save=save, suggested_name=suggested_name, file_kind=file_kind
    )


def save_staged_file_native(
    self: DesktopApi,
    token: str,
    suggested_name: str,
    file_kind: str,
    save_as: bool = False,
) -> dict[str, object]:
    """Save staged content without calling pywebview GUI APIs from FastAPI threads."""
    suffix = ".docx" if file_kind == "word" else ".ddgproj"
    try:
        source = staged_path(token, suffix)
    except (ValueError, FileNotFoundError):
        return {"saved": False, "error": "保存対象の一時ファイルが見つかりません。"}

    destination: Path | None = None
    if file_kind == "project" and self.current_project_path is not None and not save_as:
        destination = self.current_project_path
    else:
        try:
            destination = _choose_path(
                self,
                save=True,
                suggested_name=suggested_name,
                file_kind=file_kind,
            )
        except Exception as exc:
            return {"saved": False, "error": f"保存ダイアログを開けませんでした: {exc}"}

    if destination is None:
        return {"saved": False, "cancelled": True}
    if destination.suffix.lower() != suffix:
        destination = destination.with_suffix(suffix)

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        remove_staged_file(source)
        if file_kind == "project":
            self.current_project_path = destination
        return {
            "saved": True,
            "path": str(destination.resolve()),
            "filename": destination.name,
        }
    except OSError as exc:
        return {"saved": False, "error": f"ファイルを保存できませんでした: {exc}"}


def open_project_file_native(self: DesktopApi) -> dict[str, object]:
    """Open a project through Win32 common dialog without touching pywebview UI APIs."""
    try:
        source = _choose_path(self, save=False, file_kind="project")
    except Exception as exc:
        return {"opened": False, "error": f"ファイル選択ダイアログを開けませんでした: {exc}"}

    if source is None:
        return {"opened": False, "cancelled": True}
    try:
        project = read_project_archive(source)
        payload = json.dumps(project, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        token, _path = stage_bytes(payload, ".json")
        self.current_project_path = source
        return {"opened": True, "token": token, "filename": source.name}
    except (OSError, ValueError) as exc:
        return {"opened": False, "error": str(exc)}


# Runtime patch: run_local imports this module before launching the desktop app.
DesktopApi.save_staged_file = save_staged_file_native
DesktopApi.open_project_file = open_project_file_native
