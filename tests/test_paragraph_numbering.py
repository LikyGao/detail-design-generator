import io
import importlib.util
import sys
import unittest
from pathlib import Path


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

    def test_template_output_uses_literal_prefixes_without_effective_numbering(self):
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx is not installed")
        from docx import Document

        from tools.chapter_parser import _numbering_values
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

        expected = ["（1） バックアップ", "① OS", "② データ", "（2） リストア", "① 設定"]
        paragraphs = {
            paragraph.text: paragraph
            for paragraph in Document(io.BytesIO(output)).paragraphs
            if paragraph.text in expected
        }

        self.assertEqual(list(paragraphs), expected)
        for paragraph in paragraphs.values():
            self.assertIsNone(_numbering_values(paragraph))

    def test_body_paragraph_fallback_indents_increase_by_level(self):
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx is not installed")
        from docx import Document

        from tools.chapter_parser import _numbering_values
        from tools.docx_builder import _add_body_paragraph, PARAGRAPH_FALLBACK_INDENTS

        document = Document()
        counters = {}
        for level in range(7):
            _add_body_paragraph(
                document,
                {"paragraph_style": f"level_{level}", "text": f"level {level}"},
                {},
                counters,
            )

        indents = [paragraph.paragraph_format.left_indent.twips for paragraph in document.paragraphs]
        self.assertEqual(indents, list(PARAGRAPH_FALLBACK_INDENTS.values()))
        self.assertEqual(indents, sorted(set(indents)))
        for paragraph in document.paragraphs:
            self.assertIsNone(_numbering_values(paragraph))

    def test_body_paragraph_prefers_original_indents_and_removes_prototype_numbering(self):
        if importlib.util.find_spec("docx") is None:
            self.skipTest("python-docx is not installed")
        from copy import deepcopy

        from docx import Document
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        from tools.chapter_parser import _numbering_values
        from tools.docx_builder import _add_body_paragraph

        document = Document()
        source = document.add_paragraph(style="Normal")
        num_properties = OxmlElement("w:numPr")
        num_id = OxmlElement("w:numId")
        num_id.set(qn("w:val"), "1")
        num_properties.append(num_id)
        source._p.get_or_add_pPr().append(num_properties)
        prototype = deepcopy(source._p.pPr)
        source._element.getparent().remove(source._element)

        _add_body_paragraph(
            document,
            {
                "paragraph_style": "level_2",
                "text": "original indent",
                "left_indent_twips": 975,
                "first_line_indent_twips": 120,
            },
            {"level_2": prototype},
            {},
        )
        _add_body_paragraph(
            document,
            {
                "paragraph_style": "level_3",
                "text": "hanging indent",
                "left_indent_twips": 1230,
                "first_line_indent_twips": 90,
                "hanging_indent_twips": 240,
            },
            {"level_3": prototype},
            {},
        )

        first, hanging = document.paragraphs
        self.assertEqual(first.paragraph_format.left_indent.twips, 975)
        self.assertEqual(first.paragraph_format.first_line_indent.twips, 120)
        self.assertEqual(hanging.paragraph_format.left_indent.twips, 1230)
        self.assertEqual(hanging.paragraph_format.first_line_indent.twips, -240)
        self.assertIsNone(_numbering_values(first))
        self.assertIsNone(_numbering_values(hanging))


if __name__ == "__main__":
    unittest.main()
