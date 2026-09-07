from fastapi.testclient import TestClient

from local_backend.app import create_app


class FakeDesktopApi:
    def __init__(self):
        self.calls = []

    def open_preview_window(self):
        self.calls.append(("preview",))
        return {"opened": True, "existing": False}

    def save_staged_file(self, token, suggested_name, file_kind, save_as=False):
        self.calls.append(("save", token, suggested_name, file_kind, save_as))
        return {
            "saved": True,
            "path": r"C:\\Temp\\output.docx",
            "filename": "output.docx",
        }

    def open_project_file(self):
        self.calls.append(("open_project",))
        return {"opened": True, "token": "abc", "filename": "case.ddgproj"}

    def clear_current_project_path(self):
        self.calls.append(("clear_project",))
        return {"ok": True}


def test_desktop_routes_require_desktop_runtime(tmp_path):
    client = TestClient(create_app(data_root=tmp_path))
    response = client.post("/api/desktop/preview/open")
    assert response.status_code == 503
    assert "デスクトップ機能" in response.json()["detail"]


def test_desktop_native_actions_route_through_backend(tmp_path):
    desktop = FakeDesktopApi()
    client = TestClient(create_app(data_root=tmp_path, desktop_api=desktop))

    preview = client.post("/api/desktop/preview/open")
    assert preview.status_code == 200
    assert preview.json() == {"opened": True, "existing": False}

    saved = client.post(
        "/api/desktop/file/save",
        json={
            "token": "tok123",
            "suggested_name": "output.docx",
            "file_kind": "word",
            "save_as": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["saved"] is True
    assert saved.json()["path"].endswith("output.docx")

    opened = client.post("/api/desktop/project/open")
    assert opened.status_code == 200
    assert opened.json()["opened"] is True

    cleared = client.post("/api/desktop/project/clear-path")
    assert cleared.status_code == 200
    assert cleared.json() == {"ok": True}

    assert desktop.calls == [
        ("preview",),
        ("save", "tok123", "output.docx", "word", True),
        ("open_project",),
        ("clear_project",),
    ]


def test_http_compatibility_patch_is_served_and_injected(tmp_path):
    client = TestClient(create_app(data_root=tmp_path))
    root = client.get("/")
    assert root.status_code == 200
    assert '<script src="/desktop-http-api-patch.js"></script>' in root.text

    patch = client.get("/desktop-http-api-patch.js")
    assert patch.status_code == 200
    assert "/api/desktop/preview/open" in patch.text
    assert "/api/desktop/file/save" in patch.text
    assert "/api/desktop/project/open" in patch.text
    assert "open_preview_window" in patch.text
    assert "save_staged_file" in patch.text
