from fastapi.testclient import TestClient

from local_backend.app import create_app


def test_template_status_payload_stays_small_when_metadata_exists(tmp_path):
    directory = tmp_path / "server_storage"
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        '{"id":"id1","filename":"template.docx","template_version":"2.1","section_content_summary":{"section_count":142}}',
        encoding="utf-8",
    )
    response = TestClient(create_app(data_root=tmp_path)).post(
        "/api/templates/status", json={"document_type": "server_storage"}
    )
    response.raise_for_status()
    assert len(response.content) < 2048
