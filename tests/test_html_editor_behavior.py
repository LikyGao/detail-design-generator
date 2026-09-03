import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "基本設計書generator.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


def _function(name: str) -> str:
    start = HTML.index(f"function {name}(")
    brace = HTML.index("){", start) + 1
    depth = 0
    for index in range(brace, len(HTML)):
        if HTML[index] == "{":
            depth += 1
        elif HTML[index] == "}":
            depth -= 1
            if depth == 0:
                return HTML[start:index + 1]
    raise AssertionError(f"unterminated JavaScript function: {name}")


def _run_node(source: str):
    result = subprocess.run(
        ["node", "-e", source], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return json.loads(result.stdout)


def test_paragraph_edit_css_is_scoped_to_direct_children():
    required = [
        ".paragraph-item:not(.is-editing)>.block>.block-body>.paragraph-editor>.paragraph-style-select",
        ".paragraph-item:not(.is-editing)>.block>.block-body>.paragraph-editor>.ci-input",
        ".paragraph-item.is-editing>.block>.block-body>.paragraph-read",
    ]
    for selector in required:
        assert selector in HTML
    assert ".paragraph-item:not(.is-editing) .paragraph-style-select" not in HTML
    assert ".paragraph-item.is-editing .paragraph-read" not in HTML


def test_activate_edit_target_selects_actual_block_and_only_its_direct_wrapper():
    function = _function("activateEditTarget")
    source = f"""
let activeEditTarget=null;
class Classes {{
  constructor(...names) {{ this.value=new Set(names); }}
  add(name) {{ this.value.add(name); }}
  remove(name) {{ this.value.delete(name); }}
  contains(name) {{ return this.value.has(name); }}
}}
const wrappers={{}}, blocks={{}};
for(const id of ['parent','child','grandchild']) {{
  wrappers[id]={{classList:new Classes('paragraph-item')}};
  blocks[id]={{classList:new Classes('block'),parentElement:wrappers[id],querySelector:()=>null}};
}}
const document={{
  querySelectorAll:()=>Object.values(wrappers).concat(Object.values(blocks)).filter(x=>x.classList.contains('is-editing')),
  querySelector:selector=>{{
    const match=selector.match(/data-block-id="([^"]+)"/);
    return match?blocks[match[1]]:null;
  }}
}};
const CSS={{escape:value=>String(value)}};
const requestAnimationFrame=callback=>callback();
{function}
const snapshots=[];
for(const id of ['parent','child','grandchild']) {{
  activateEditTarget({{kind:'block',nodeId:'section',blockId:id}},{{focus:false}});
  snapshots.push({{
    id,
    wrappers:Object.fromEntries(Object.entries(wrappers).map(([key,value])=>[key,value.classList.contains('is-editing')])),
    blocks:Object.fromEntries(Object.entries(blocks).map(([key,value])=>[key,value.classList.contains('is-editing')]))
  }});
}}
console.log(JSON.stringify(snapshots));
"""
    snapshots = _run_node(source)
    for snapshot in snapshots:
        chosen = snapshot["id"]
        assert [key for key, value in snapshot["wrappers"].items() if value] == [chosen]
        assert [key for key, value in snapshot["blocks"].items() if value] == [chosen]


def test_document_numbering_continues_level_one_per_top_chapter_and_restarts_groups():
    names = [
        "getParagraphNativeIlvl", "getParagraphStyleConfig", "paragraphNumberStart",
        "calculateParagraphNumbering", "calculateDocumentParagraphNumbering",
    ]
    functions = "\n".join(_function(name) for name in names)
    source = f"""
const PARAGRAPH_STYLE_CONFIGS={{
 level_0:{{symbol:'',numbered:false}}, level_1:{{symbol:'',numbered:true}},
 level_2:{{symbol:'・',numbered:false}}, level_3:{{symbol:'➢',numbered:false}},
 level_4:{{symbol:'',numbered:true}}, level_5:{{symbol:'・',numbered:false}},
 level_6:{{symbol:'',numbered:true}}
}};
const PARAGRAPH_STYLE_TO_NATIVE_ILVL={{level_1:0,level_2:1,level_4:2,level_3:3,level_5:4,level_6:5}};
{functions}
const p=(id,style,extra={{}})=>Object.assign({{id,type:'paragraph',paragraph_style:style}},extra);
const chapters=[
 {{id:'chapter-6',blocks:[p('a1','level_1'),p('a2','level_1')],children:[
   {{id:'6-1',blocks:[p('a3','level_1')],children:[{{id:'6-1-1',blocks:[p('a4','level_1')],children:[]}}]}},
   {{id:'6-3',blocks:[p('ga1','level_4',{{list_group_id:'group-A',num_id:'shared'}}),p('ga2','level_4',{{list_group_id:'group-A',num_id:'shared'}}),p('separator','level_2'),p('gb1','level_4',{{list_group_id:'group-B',num_id:'shared'}}),p('gb2','level_4',{{list_group_id:'group-B',num_id:'shared'}})],children:[]}}
 ]}},
 {{id:'chapter-7',blocks:[p('b1','level_1')],children:[]}}
];
const result=calculateDocumentParagraphNumbering(chapters);
console.log(JSON.stringify(Object.fromEntries(result)));
"""
    prefixes = _run_node(source)
    assert [prefixes[key] for key in ("a1", "a2", "a3", "a4")] == ["（1）", "（2）", "（3）", "（4）"]
    assert prefixes["b1"] == "（1）"
    assert [prefixes[key] for key in ("ga1", "ga2", "gb1", "gb2")] == ["①", "②", "①", "②"]
