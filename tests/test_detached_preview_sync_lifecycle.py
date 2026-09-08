from __future__ import annotations

import re
import subprocess
from pathlib import Path

from local_backend.app import _preview_window_html

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "local_backend" / "desktop_http_api_patch.js"


def test_detached_preview_scrolls_on_target_change_even_without_content_revision():
    html = _preview_window_html()

    assert 'data-preview-nodeid' in html
    assert 'data-preview-block-id' in html
    assert "const targetChanged = nextTargetSignature !== targetSignature;" in html
    assert "if((contentChanged || targetChanged) && state.nodeId)" in html
    assert "scrollIntoView" in html
    assert "block: 'center'" in html


def test_detached_preview_closes_when_main_window_sends_close_sentinel():
    html = _preview_window_html()
    patch = PATCH.read_text(encoding="utf-8")

    sentinel = "__DDG_MAIN_WINDOW_CLOSED__"
    assert sentinel in html
    assert sentinel in patch
    assert "window.close();" in html
    assert "window.addEventListener('pagehide', notifyDetachedPreviewMainClosed)" in patch
    assert "window.addEventListener('beforeunload', notifyDetachedPreviewMainClosed)" in patch
    assert "navigator.sendBeacon" in patch


def test_editor_target_publication_is_forwarded_to_local_preview_state():
    patch = PATCH.read_text(encoding="utf-8")

    assert "typeof publishPreviewTarget !== 'function'" in patch
    assert "publishPreviewTarget = function desktopHttpPublishPreviewTarget" in patch
    assert "pushDetachedPreviewTarget();" in patch
    assert "currentPreviewState()" in patch
    assert "'/api/preview-state'" in patch


def test_detached_preview_inline_script_is_valid_javascript(tmp_path: Path):
    html = _preview_window_html()
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    assert scripts

    script_path = tmp_path / "preview-window.js"
    script_path.write_text("\n".join(scripts), encoding="utf-8")
    subprocess.run(["node", "--check", str(script_path)], check=True)
