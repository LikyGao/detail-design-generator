from pathlib import Path

from local_backend.app import HTML_FILENAME, _desktop_html, resource_path


def test_desktop_scripts_are_injected_before_final_body_close():
    source_path: Path = resource_path(HTML_FILENAME)
    source = source_path.read_text(encoding="utf-8")
    bridge_tag = '<script src="/local-bridge.js"></script>'
    patch_tag = '<script src="/template-manager-patch.js"></script>'
    body_end = source.rfind("</body>")

    assert body_end != -1
    expected = (
        source[:body_end]
        + f"  {bridge_tag}\n"
        + f"  {patch_tag}\n"
        + source[body_end:]
    )
    rendered = _desktop_html()

    assert rendered == expected
    bridge_pos = rendered.rfind(bridge_tag)
    patch_end = rendered.rfind(patch_tag) + len(patch_tag)
    rendered_body_end = rendered.rfind("</body>")
    assert bridge_pos < patch_end < rendered_body_end
    assert rendered[patch_end:rendered_body_end].strip() == ""
