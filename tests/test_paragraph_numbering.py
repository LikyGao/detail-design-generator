import io
import importlib.util
import sys
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "personal" / "standard_word_generator"
sys.path.insert(0, str(PLUGIN_ROOT))

from tools.paragraph_numbering import calculate_paragraph_prefix


class ParagraphNumberingTest(unittest.TestCase):
    def prefixes(self, styles):
        counters = {}
        return [calculate_paragraph_prefix(style, counters) for style in styles]

    def test_nested_numbering_and_continuation(self):
        self.assertEqual(
            self.prefixes(
                ["level_1", "level_2", "level_3", "level_4", "level_5", "level_4", "level_1"]
            ),
            ["（1）", "・", "➢", "①", "・", "②", "（2）"],
        )

    def test_parent_restarts_deeper_numbering(self):
        self.assertEqual(
            self.prefixes(["level_1", "level_4", "level_4", "level_1", "level_4"]),
            ["（1）", "①", "②", "（2）", "①"],
        )

    def test_template_output_uses_literal_prefixes_without_num_pr(self):
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx is not installed")
        from tools.docx_builder import generate_standard_docx

        template = PLUGIN_ROOT / "templates" / "基本設計書_template.docx"
        blocks = [
            {"type": "paragraph", "paragraph_style": style, "text": text}
            for style, text in [
                ("level_1", "バックアップ"),
                ("level_4", "OS"),
                ("level_4", "データ"),
                ("level_1", "リストア"),
                ("level_4", "設定"),
            ]
        ]
        output = generate_standard_docx(
            template,
            client_name="test",
            project_name="test",
            chapters=[{"level": 1, "title": "test", "blocks": blocks}],
        )

        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            document_xml = archive.read("word/document.xml")
            self.assertTrue(archive.read("word/numbering.xml"))

        root = ElementTree.fromstring(document_xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        expected = ["（1） バックアップ", "① OS", "② データ", "（2） リストア", "① 設定"]
        paragraphs = {}
        for paragraph in root.findall(".//w:body/w:p", ns):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
            if text in expected:
                paragraphs[text] = paragraph

        self.assertEqual(list(paragraphs), expected)
        for paragraph in paragraphs.values():
            self.assertIsNone(paragraph.find("./w:pPr/w:numPr", ns))


if __name__ == "__main__":
    unittest.main()
