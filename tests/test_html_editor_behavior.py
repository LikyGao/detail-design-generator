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


def test_paragraph_edit_css_matches_real_dom_and_is_scoped_to_current_item():
    required = [
        ".paragraph-item:not(.is-editing)>.block>.block-body>.paragraph-editor>.paragraph-style-select",
        ".paragraph-item:not(.is-editing)>.block>.block-body>.paragraph-editor>.ci-input",
        ".paragraph-item.is-editing>.block>.block-body>.paragraph-editor>.paragraph-read",
    ]
    for selector in required:
        assert selector in HTML
    assert ".paragraph-item:not(.is-editing) .paragraph-style-select" not in HTML
    assert ".paragraph-item.is-editing .paragraph-read" not in HTML
    # buildBlock appends read view inside paragraph-editor, not block-body.
    assert "row.appendChild(summary); row.appendChild(read);" in HTML
    assert "bb.appendChild(row); bb.appendChild(aiFix)" in HTML


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


def test_document_numbering_restarts_level_one_for_every_node_and_hierarchy():
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
   {{id:'6-3',blocks:[p('parent-a','level_2'),p('ga1','level_4',{{list_group_id:'same',num_id:'shared'}}),p('ga2','level_4',{{list_group_id:'same',num_id:'shared'}}),p('parent-b','level_2'),p('parent-c','level_2'),p('parent-d','level_2'),p('gb1','level_4',{{list_group_id:'same',num_id:'shared'}}),p('gb2','level_4',{{list_group_id:'same',num_id:'shared'}}),p('gb3','level_4',{{list_group_id:'same',num_id:'shared'}})],children:[]}}
 ]}},
 {{id:'chapter-7',blocks:[p('b1','level_1')],children:[]}}
];
const result=calculateDocumentParagraphNumbering(chapters);
console.log(JSON.stringify(Object.fromEntries(result)));
"""
    prefixes = _run_node(source)
    assert [prefixes[key] for key in ("a1", "a2", "a3", "a4")] == ["（1）", "（2）", "（1）", "（1）"]
    assert prefixes["b1"] == "（1）"
    assert [prefixes[key] for key in ("ga1", "ga2", "gb1", "gb2", "gb3")] == ["①", "②", "①", "②", "③"]



def test_media_permissions_are_content_type_driven():
    functions = "\n".join(_function(name) for name in (
        "getParagraphNativeIlvl", "getParagraphContentType", "canAttachMedia"
    ))
    source = f"""
const PARAGRAPH_STYLE_TO_NATIVE_ILVL={{level_1:0,level_2:1,level_4:2,level_3:3,level_5:4,level_6:5}};
{functions}
const result={{}};
for(const style of ['level_0','level_1','level_2','level_4','level_3','level_5','level_6']) {{
  result[style]=canAttachMedia({{type:'paragraph',paragraph_style:style}});
}}
result.heading=canAttachMedia({{type:'heading'}});
console.log(JSON.stringify(result));
"""
    assert _run_node(source) == {
        "level_0": True,   # explanation
        "level_1": False,  # Style0
        "level_2": True,   # Style1
        "level_4": True,   # Style2
        "level_3": True,   # Style3
        "level_5": True,   # Style4
        "level_6": False,
        "heading": False,
    }


def test_media_ownership_migrates_legacy_blocks_and_preserves_order():
    functions = "\n".join(_function(name) for name in (
        "getParagraphNativeIlvl", "getParagraphContentType", "canAttachMedia",
        "normalizeMediaOwnership"
    ))
    source = f"""
const PARAGRAPH_STYLE_TO_NATIVE_ILVL={{level_1:0,level_2:1,level_4:2,level_3:3,level_5:4,level_6:5}};
{functions}
const blocks=[
 {{id:'style0',type:'paragraph',paragraph_style:'level_1'}},
 {{id:'explanation',type:'paragraph',paragraph_style:'level_0'}},
 {{id:'table',type:'table'}},{{id:'figure',type:'figure'}},{{id:'table2',type:'table'}}
];
normalizeMediaOwnership(blocks);
console.log(JSON.stringify(blocks.slice(2).map(block=>[block.id,block.parent_block_id])));
"""
    assert _run_node(source) == [
        ["table", "explanation"], ["figure", "explanation"], ["table2", "explanation"]
    ]


def test_editor_nests_owned_media_and_restricts_explanation_drag_scope():
    hierarchy = _function("renderBlockHierarchy")
    sorter = _function("initParagraphSortables")
    node_menu = _function("buildNodeAddMenu")
    block_builder = _function("buildBlock")
    assert "attachments.get(b.id)||[]" in hierarchy
    assert "paragraph-attachments" in HTML
    assert "root.querySelector(':scope > .explanation-list')" in sorter
    assert "row.appendChild(drag); row.appendChild(summary)" in block_builder
    assert "if(canAttachMedia(b))" in block_builder
    assert "addTableBlock" not in node_menu
    assert "addFigureBlock" not in node_menu


def test_compact_drag_view_hides_duplicate_and_nested_paragraph_content():
    assert ".paragraph-item.drag-compact>.block>.block-body .paragraph-read{display:none}" in HTML
    assert ".paragraph-item.drag-compact>.paragraph-attachments,.paragraph-item.drag-compact>.paragraph-children{display:none}" in HTML
    assert ".paragraph-item.drag-compact>.block>.block-body .paragraph-drag-summary{display:block;flex:1}" in HTML
    assert ".chapter-sort-scope>.node-card.drag-compact>.node-title-row .node-title-display{display:none}" in HTML


def test_chapter_and_paragraph_share_transactional_free_scroll_lifecycle():
    chapter_sorter = _function("initChapterSortables")
    paragraph_sorter = _function("initParagraphSortables")

    for sorter, drag_type in ((chapter_sorter, "chapter"), (paragraph_sorter, "paragraph")):
        assert "scroll:scrollContainer" in sorter
        assert "forceAutoScrollFallback:true" in sorter
        assert "beginDragSession" in sorter
        assert "startCardDrag" in sorter
        assert "finishDragSession" in sorter
        assert "onMove:markSortableMove" in sorter
        assert f"type:'{drag_type}'" in sorter
    assert "getDragAllowedRect" not in HTML
    assert "runBoundedDragScroll" not in HTML
    assert "draggable:':scope > .node-card'" not in chapter_sorter
    assert "data-chapter-sort-scope" in chapter_sorter


def test_drag_transaction_starts_on_start_instead_of_on_choose():
    chapter_sorter = _function("initChapterSortables")
    paragraph_sorter = _function("initParagraphSortables")

    for sorter in (chapter_sorter, paragraph_sorter):
        assert "onChoose:" not in sorter
        on_start = sorter.index("onStart:")
        begin = sorter.index("beginDragSession", on_start)
        start = sorter.index("startCardDrag", on_start)
        assert on_start < begin < start


def test_preview_uses_word_like_headings_half_em_levels_and_hanging_layout():
    assert "--preview-indent-unit:0.5em" in HTML
    assert "margin-left:calc(var(--preview-level,0) * var(--preview-indent-unit))" in HTML
    assert ".word-paragraph{display:grid;grid-template-columns:auto minmax(0,1fr)" in HTML
    assert ".word-paragraph-text{grid-column:2" in HTML
    assert "border-left:4px solid #444" not in HTML
    assert "border-bottom:2px solid #333" not in HTML
    preview = _function("buildPreviewHtml")
    blocks = _function("blocksToHtml")
    assert "（本文未入力）" not in preview
    assert "if(!String(b.text||'').trim()) return '';" in blocks


def test_step2_attention_is_pale_pink_and_has_no_exclamation_marker():
    nav = _function("renderNav")
    selector = _function("buildChapterSelectCard")
    assert ".step2-attention{background:#fff3f5!important" in HTML
    assert "classList.add('step2-attention')" in nav
    assert "classList.add('step2-attention')" in selector
    assert "warning.textContent='!'" not in nav


def test_media_caption_ui_and_filename_default_are_consistent():
    table = _function("buildTableEditor")
    figure = _function("buildFigureEditor")
    row = _function("buildMediaCaptionRow")
    picker = _function("onPickImage")
    assert "mediaCaptionText(b)" in table and "buildMediaCaptionRow(n,b" in table
    assert "mediaCaptionText(b)" in figure and "buildMediaCaptionRow(n,b" in figure
    assert "del.textContent='×'" in row
    assert "b.caption===previousDefault" in picker
    assert "b.caption=fileNameWithoutExtension(f.name)" in picker
    assert "📎" not in figure


def test_filename_caption_default_preserves_manual_caption_on_replacement():
    function = _function("fileNameWithoutExtension")
    source = f"""
{function}
const update=(block,name)=>{{
  const previousDefault=fileNameWithoutExtension(block.fileName);
  if(!String(block.caption||'').trim()||block.caption===previousDefault) block.caption=fileNameWithoutExtension(name);
  block.fileName=name;
}};
const automatic={{caption:'',fileName:''}};
update(automatic,'Catalyst 9200CX.png');
update(automatic,'Cisco9200CX.png');
const manual={{caption:'catalyst',fileName:'Catalyst 9200CX.png'}};
update(manual,'Cisco9200CX.png');
console.log(JSON.stringify({{automatic,manual,path:fileNameWithoutExtension('folder/構成図.final.PNG')}}));
"""
    result = _run_node(source)
    assert result["automatic"]["caption"] == "Cisco9200CX"
    assert result["manual"]["caption"] == "catalyst"
    assert result["path"] == "構成図.final"


def test_drag_transaction_keeps_origin_and_only_commits_valid_changed_drop():
    begin = _function("beginDragSession")
    finish = _function("finishDragSession")
    rollback = _function("rollbackDragSession")
    valid_target = _function("updateDragValidTarget")

    assert "originPreviousSiblingId" in begin
    assert "originNextSiblingId" in begin
    assert "originalOrder" in begin
    assert "drag-origin-marker" in begin
    assert "元の位置" in begin
    assert "session.validTarget" in valid_target
    assert "drag-valid-target" in valid_target
    assert "if(!valid) restoreOriginalDom(session)" in finish
    assert "if(valid&&changed){ commit()" in finish
    assert "restoreOriginalDom(session)" in rollback
    assert ".drag-valid-target .chapter-sort-ghost:before{content:'ここに移動'" in HTML
