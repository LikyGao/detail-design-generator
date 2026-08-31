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


if __name__ == "__main__":
    unittest.main()
