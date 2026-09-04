import io
import json
import re
import subprocess
import sys
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "基本設計書generator.html"
PLUGIN_ROOT = ROOT / "plugins/personal/standard_word_generator"
TEMPLATE_PATH = PLUGIN_ROOT / "templates/基本設計書_template.docx"
sys.path.insert(0, str(PLUGIN_ROOT))
HAS_PYTHON_DOCX = importlib.util.find_spec("docx") is not None


EXPECTED_FILENAME = "〇〇製造株式会社_基本設計書_3.4.docx"


def _javascript_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function: {name}")


def test_browser_uses_one_canonical_versioned_filename_for_ui_payload_and_download():
    html = HTML_PATH.read_text(encoding="utf-8")
    functions = "\n".join(
        _javascript_function(html, name)
        for name in (
            "sanitizeWordFilenamePart",
            "buildWordOutputFilename",
            "canonicalWordOutputFilename",
        )
    )
    script = f"""
{functions}
const cover={{client_name:'〇〇製造株式会社',version:'3.4',project_no:'243423432',file_name:'legacy_243423432.docx'}};
console.log(JSON.stringify({{
  built:buildWordOutputFilename(cover),
  canonical:canonicalWordOutputFilename(cover)
}}));
"""
    output = subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    assert json.loads(output) == {"built": EXPECTED_FILENAME, "canonical": EXPECTED_FILENAME}

    assert 'output_filename:outputFilename' in html
    assert 'cover.file_name=outputFilename' in html
    assert 'downloadBlob(blob,outputFilename)' in html
    assert 'a.href=url; a.download=outputFilename' in html
    assert re.search(r'id="cv-filename"[^>]*\breadonly\b', html)


@pytest.mark.skipif(not HAS_PYTHON_DOCX, reason="python-docx is required for DOCX regression tests")
def test_generated_docx_cover_has_exactly_one_filename_and_separate_project_number():
    from docx import Document
    from tools.docx_builder import generate_standard_docx

    generated = generate_standard_docx(
        TEMPLATE_PATH,
        client_name="〇〇製造株式会社",
        project_name="テストプロジェクト",
        version="3.4",
        issue_date="2026/09/04",
        file_name=EXPECTED_FILENAME,
        project_no="243423432",
        revisions=[],
        chapters=[],
    )
    document = Document(io.BytesIO(generated))
    property_table = document.tables[0]

    assert property_table.rows[0].cells[2].text == "3.4"
    filename_cell = property_table.rows[2].cells[2]
    assert filename_cell.text == EXPECTED_FILENAME
    assert filename_cell.text.count(EXPECTED_FILENAME) == 1
    assert "243423432" not in filename_cell.text
    assert property_table.rows[3].cells[2].text == "243423432"

    # The original filename value is inside a Word field. Replacement must
    # remove every alternate text-bearing structure, not merely blank runs.
    assert not filename_cell._tc.xpath(".//w:fldSimple | .//w:fldChar | .//w:sdt")
    text_nodes = filename_cell._tc.xpath(".//w:t")
    assert "".join(node.text or "" for node in text_nodes) == EXPECTED_FILENAME
    assert len(text_nodes) == 1


def test_workflow_dependency_version_is_explicitly_audited():
    workflow = (ROOT / "dify/personal/workflows/基本設計書_Word生成API.yml").read_text(
        encoding="utf-8"
    )
    manifest = (PLUGIN_ROOT / "manifest.yaml").read_text(encoding="utf-8")
    assert "likygao/standard_word_generator:0.0.10@" in workflow
    assert manifest.startswith("version: 0.0.24\n")
