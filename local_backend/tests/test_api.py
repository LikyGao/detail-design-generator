import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DETAIL_DESIGN_DATA_DIR", str(tmp_path))
    import local_backend.app as module
    importlib.reload(module)
    return TestClient(module.app)


@pytest.fixture()
def template_bytes():
    return (Path(__file__).parents[2] / "plugins/personal/standard_word_generator/templates/基本設計書_template.docx").read_bytes()


def register(client, template_bytes, document_type="server_storage"):
    return client.post("/api/templates/register", data={"document_type": document_type, "template_version": "1.0"},
                       files={"template_file": ("standard_v1.0.docx", template_bytes,
                                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("document_type", ["server_storage", "network", "cloud", "full"])
def test_register_and_get_each_document_type(client, template_bytes, document_type):
    response = register(client, template_bytes, document_type)
    assert response.status_code == 200, response.text
    result = client.post("/api/template-data", json={"document_type": document_type})
    assert result.status_code == 200
    assert {"template_id", "template_version", "master_json", "chapter_list_json", "section_contents_json"} <= result.json().keys()


def test_missing_template_is_clear(client):
    response = client.post("/api/template-data", json={"document_type": "network"})
    assert response.status_code == 404
    assert "未登録" in response.json()["detail"]


def test_generate_word_is_docx(client, template_bytes):
    assert register(client, template_bytes).status_code == 200
    response = client.post("/api/generate-word", json={
        "document_type": "server_storage", "chapters_json": "[]",
        "revision_history_json": "[]", "output_filename": "test.docx",
    })
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"PK")
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in response.headers["content-type"]


def test_html_has_no_personal_dify_runtime_url():
    html = (Path(__file__).parents[2] / "基本設計書generator.html").read_text(encoding="utf-8")
    assert "https://api.dify.ai/v1/workflows/run" not in html
    assert "https://api.dify.ricoh.com/v1/workflows/run" in html
