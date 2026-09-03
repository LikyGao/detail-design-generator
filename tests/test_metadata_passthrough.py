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

    def test_dify_normalization_keeps_required_native_metadata_only(self):
        namespace = {}
        exec(workflow_codes()[0], namespace)
        item = {"type": "paragraph", "paragraph_style": "level_4", "text": "body", **self.metadata}
        result = namespace["paragraph_blocks_from_list"]([json.loads(json.dumps(item))])[0]
        for key in ("word_style_id", "word_style_name", "native_ilvl", "num_id", "abstract_num_id", "list_group_id"):
            self.assertEqual(result[key], self.metadata[key])
        for redundant in ("word_style_based_on_id", "numbering_p_style", "symbol_font", "left_indent_twips", "first_line_indent_twips", "hanging_indent_twips", "future_word_field"):
            self.assertNotIn(redundant, result)

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


class LargePayloadChunkingTest(unittest.TestCase):
    max_chunk_size = 120000

    @classmethod
    def setUpClass(cls):
        codes = workflow_codes()
        cls.parse_node = {}
        cls.merge_node = {}
        exec(codes[0], cls.parse_node)
        exec(codes[1], cls.merge_node)

    def build_large_payload(self):
        paragraphs = []
        for index in range(520):
            paragraphs.append({
                "type": "paragraph",
                "text": f"第{index}段落：" + ("日本語の標準本文を安全に保持します。" * 22),
                "paragraph_style": "level_4",
                "word_style_id": "NativeList2",
                "word_style_name": "標準リスト二階層",
                "native_ilvl": 2,
                "num_id": "42",
                "abstract_num_id": "7",
                "list_group_id": "word:42",
                "numbering_start": 1,
                "start_override": None,
                "level_restart": False,
                "marker_type": "bullet",
                # These are template-canonical and must not be repeated downstream.
                "word_style_based_on_id": "NativeList1",
                "numbering_p_style": "NativeList2",
                "symbol_font": "Wingdings",
                "number_format": "bullet",
                "level_text": "・",
                "left_indent_twips": 720,
                "first_line_indent_twips": 0,
                "hanging_indent_twips": 180,
            })
        sections = [{"source_template_number": "6", "paragraphs": paragraphs}]
        tree = [{"id": "chapter-6", "source_template_number": "6", "title": "第6章", "level": 1, "source": "standard", "children": []}]
        return tree, sections, paragraphs

    def test_large_reference_and_result_round_trip_without_truncation(self):
        tree, sections, source_paragraphs = self.build_large_payload()
        self.assertGreater(len(json.dumps(sections, ensure_ascii=False)), 160000)
        parsed = self.parse_node["main"](
            json.dumps({"stage": "generate", "confirmed_chapter_tree": tree}, ensure_ascii=False),
            "server_storage", "template", "1", json.dumps(sections, ensure_ascii=False), ""
        )

        reference_parts = [parsed[f"standard_reference_json_part_{i}"] for i in range(1, 7)]
        self.assertTrue(all(not isinstance(value, str) or len(value) <= self.max_chunk_size for value in parsed.values()))
        self.assertEqual(parsed["standard_reference_json"], "")
        self.assertTrue(all(len(part) <= self.max_chunk_size for part in reference_parts))
        references = json.loads("".join(reference_parts))
        transferred = references[0]["standard_blocks"]
        self.assertEqual(len(transferred), len(source_paragraphs))
        self.assertEqual([p["text"] for p in transferred], [p["text"] for p in source_paragraphs])
        for key in ("word_style_id", "word_style_name", "native_ilvl", "list_group_id"):
            self.assertEqual(transferred[-1][key], source_paragraphs[-1][key])
        for redundant in ("word_style_based_on_id", "numbering_p_style", "symbol_font", "number_format", "level_text", "left_indent_twips", "first_line_indent_twips", "hanging_indent_twips"):
            self.assertNotIn(redundant, transferred[0])

        kwargs = {
            "confirmed_tree_json": parsed["confirmed_tree_json"],
            "standard_reference_json": parsed["standard_reference_json"],
            "cover_json": parsed["cover_json"],
            "document_plan_json": parsed["document_plan_json"],
            **{f"standard_reference_json_part_{i}": reference_parts[i - 1] for i in range(1, 7)},
        }
        merged = self.merge_node["main"](**kwargs)
        result_parts = [merged[f"result_json_part_{i}"] for i in range(1, 7)]
        self.assertTrue(all(not isinstance(value, str) or len(value) <= self.max_chunk_size for value in merged.values()))
        self.assertEqual(merged["result_json"], "")
        self.assertTrue(all(len(part) <= self.max_chunk_size for part in result_parts))
        result = json.loads("".join(result_parts))
        blocks = result["chapters"][0]["blocks"]
        self.assertEqual(len(blocks), len(source_paragraphs))
        self.assertEqual([p["text"] for p in blocks], [p["text"] for p in source_paragraphs])

    def test_small_result_keeps_legacy_result_json(self):
        output = self.merge_node["main"]("[]", "[]", "{}", "{}")
        self.assertTrue(output["result_json"])
        self.assertTrue(all(not output[f"result_json_part_{i}"] for i in range(1, 7)))
        self.assertEqual(json.loads(output["result_json"])["chapters"], [])

    def test_html_reassembles_numbered_chunks_and_paragraph_fix_keeps_metadata(self):
        html = HTML.read_text()
        self.assertIn("/^result_json_part_\\d+$/", html)
        self.assertIn(".join('')", html)
        block = {"text": "修正前", "word_style_id": "Native2", "word_style_name": "Native Two", "native_ilvl": 2, "num_id": "42", "list_group_id": "word:42"}
        metadata = {key: value for key, value in block.items() if key != "text"}
        block["text"] = "修正後"
        self.assertEqual({key: value for key, value in block.items() if key != "text"}, metadata)


if __name__ == "__main__":
    unittest.main()
