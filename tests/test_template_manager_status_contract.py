from pathlib import Path

from local_backend.services.template_service import TemplateService


def test_template_status_uses_small_metadata_mirror_only(tmp_path: Path):
    directory = tmp_path / "server_storage"
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(
        '{"id":"abc123","filename":"template.docx","template_version":"2.1","updated_at":"now","section_content_summary":{"section_count":142}}',
        encoding="utf-8",
    )
    # Deliberately do not create the full master/section payloads. The status
    # lookup must still work because the modal only needs registration metadata.
    status = TemplateService(tmp_path).get_status("server_storage")
    assert status == {
        "registered": True,
        "document_type": "server_storage",
        "template_id": "abc123",
        "template_version": "2.1",
        "returned_section_count": 142,
        "updated_at": "now",
        "filename": "template.docx",
    }
