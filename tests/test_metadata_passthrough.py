import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "dify/company/workflows/②本文生成_v4_標準本文読込.yml"
HTML = ROOT / "基本設計書generator.html"


def workflow_codes():
    source = WORKFLOW.read_text()
    needle = '        code: "'
    codes, position = [], 0
    while (start := source.find(needle, position)) >= 0:
        quote = start + len("        code: ")
        cursor, escaped = quote + 1, False
        while cursor < len(source):
            char = source[cursor]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"' and source.startswith("\n        code_language:", cursor + 1):
                break
            cursor += 1
        codes.append(json.loads(source[quote:cursor + 1]))
        position = cursor + 1
    return codes


class MetadataPassthroughTest(unittest.TestCase):
    metadata = {
        "word_style_id": "Native2", "word_style_name": "Native Two",
        "word_style_based_on_id": "Native1", "native_ilvl": 2,
        "numbering_p_style": "Native2", "symbol_font": "Wingdings",
        "num_id": "42", "abstract_num_id": "7", "list_group_id": "word:42",
        "left_indent_twips": 720, "first_line_indent_twips": 0,
        "hanging_indent_twips": 180, "future_word_field": {"opaque": True},
    }

    def test_dify_normalization_copies_unknown_metadata(self):
        namespace = {}
        exec(workflow_codes()[0], namespace)
        item = {"type": "paragraph", "paragraph_style": "level_4", "text": "body", **self.metadata}
        result = namespace["paragraph_blocks_from_list"]([json.loads(json.dumps(item))])[0]
        for key, value in self.metadata.items():
            self.assertEqual(result[key], value)

    def test_html_normalize_and_style_change_execute_in_node(self):
        html = HTML.read_text()
        start = html.index("const PARAGRAPH_STYLE_CONFIGS=")
        end = html.index("function normalizeBlocks", start)
        normalize_end = html.index("\n", html.index("}", end) + 1)
        javascript = html[start:normalize_end]
        payload = {"type": "paragraph", "paragraph_style": "level_4", "text": "body", **self.metadata}
        script = f"""
let _uid=0; function uid(){{return 'test'+_uid++;}}
{javascript}
const raw={json.dumps(payload)};
const normalized=normalizeBlock(raw);
if(normalized.future_word_field.opaque!==true || normalized.native_ilvl!==2 || normalized.word_style_id!=='Native2') process.exit(2);
applyParagraphStyleChange(normalized,'level_3');
if(normalized.native_ilvl!==3 || 'word_style_id' in normalized || 'list_group_id' in normalized) process.exit(3);
"""
        subprocess.run(["node", "-e", script], check=True)

    def test_native_hierarchy_mapping_is_not_numeric_style_suffix(self):
        source = HTML.read_text()
        self.assertIn("level_4:2,level_3:3", source)
        self.assertIn("const level=getParagraphNativeIlvl(b)", source)
        self.assertIn("item.dataset.nodeid=n.id", source)


if __name__ == "__main__":
    unittest.main()
