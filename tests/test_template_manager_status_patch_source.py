from pathlib import Path


def test_template_manager_patch_redirect_scope():
    source = Path("local_backend/template_manager_patch.js").read_text(encoding="utf-8")
    assert "managerOpen" in source
    assert "/api/template-data" in source
    assert "/api/templates/status" in source
    assert "return originalFetch(STATUS_URL, init);" in source
    assert "return originalFetch(input, init);" in source
