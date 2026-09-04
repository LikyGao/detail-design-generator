import json
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


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
    textarea_helper = _function("ensureTextareaHeight")
    context_change = _function("handleEditorNodeContextChange")
    source = f"""
let activeEditTarget=null;
let expandedParagraphAiFixTarget=null;
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
{textarea_helper}
{context_change}
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


def test_preview_uses_template_hanging_geometry_without_changing_page_width():
    assert "--preview-page-width:210mm" in HTML
    assert "--preview-page-height:297mm" in HTML
    assert "--preview-margin-left:20mm" in HTML
    assert "--preview-margin-right:20mm" in HTML
    assert "--preview-content-width:calc(var(--preview-page-width) - var(--preview-margin-left) - var(--preview-margin-right))" in HTML
    assert "width:var(--preview-page-width);min-width:var(--preview-page-width);height:var(--preview-page-height)" in HTML
    assert "padding:var(--preview-margin-top) var(--preview-margin-right) var(--preview-margin-bottom) var(--preview-margin-left)" in HTML
    assert "--preview-indent-unit:0.5em" in HTML
    assert "margin-left:var(--preview-hierarchy-offset)" in HTML
    assert ".word-paragraph{display:grid;grid-template-columns:calc(var(--preview-text-start) - var(--preview-hierarchy-offset)) minmax(0,1fr)" in HTML
    assert "column-gap:0" in HTML
    assert "padding-left:calc(var(--preview-marker-start) - var(--preview-hierarchy-offset))" in HTML
    assert ".word-paragraph-text{grid-column:2" in HTML
    assert "font-family:'Meiryo UI',Meiryo,sans-serif;font-size:var(--preview-font-size);font-weight:var(--preview-font-weight);letter-spacing:normal" in HTML
    assert "border-left:4px solid #444" not in HTML
    assert "border-bottom:2px solid #333" not in HTML
    preview = _function("buildPreviewHtml")
    blocks = _function("blocksToHtml")
    assert "（本文未入力）" not in preview
    assert "if(!String(b.text||'').trim()) return '';" in blocks


def test_template_and_preview_share_style0_through_style4_geometry():
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    template = ROOT / "plugins/personal/standard_word_generator/templates/基本設計書_template.docx"
    with zipfile.ZipFile(template) as archive:
        styles = ET.fromstring(archive.read("word/styles.xml"))
        numbering = ET.fromstring(archive.read("word/numbering.xml"))

    # Effective Word text positions come from each native style. Style0's
    # number consumes level 0's 440-twip hanging slot; later styles explicitly
    # position the text. Marker positions are the matching hanging starts.
    expected = {
        "0": (0, 440), "1": (340, 510), "2": (510, 794),
        "3": (510, 737), "4": (794, 964),
    }
    abstract_zero = numbering.find("w:abstractNum[@w:abstractNumId='0']", namespace)
    assert abstract_zero is not None
    level_zero_indent = abstract_zero.find("w:lvl[@w:ilvl='0']/w:pPr/w:ind", namespace)
    assert int(level_zero_indent.attrib[f"{{{namespace['w']}}}left"]) == 440
    assert int(level_zero_indent.attrib[f"{{{namespace['w']}}}hanging"]) == 440

    for style_id, (marker_start, text_start) in expected.items():
        style = styles.find(f"w:style[@w:styleId='{style_id}']", namespace)
        assert style is not None
        if style_id != "0":
            indent = style.find("w:pPr/w:ind", namespace)
            assert int(indent.attrib[f"{{{namespace['w']}}}left"]) == text_start
            hanging = int(indent.attrib.get(f"{{{namespace['w']}}}hanging", "0"))
            if hanging:
                assert text_start - hanging == marker_start

    geometry = re.search(r"const PREVIEW_PARAGRAPH_GEOMETRY=\{(.*?)\n\};", HTML, re.S).group(1)
    for level, positions in zip((1, 2, 4, 3, 5), expected.values()):
        marker_start, text_start = positions
        assert f"level_{level}:{{markerStartTwips:{marker_start},textStartTwips:{text_start}," in geometry

    # 170 mm = 9637.795 twips. The text column ends at the unchanged right
    # margin, so its effective width is content width minus Word text start.
    content_twips = 170 / 25.4 * 1440
    widths_mm = [(content_twips - text_start) / 1440 * 25.4 for _, text_start in expected.values()]
    assert widths_mm == pytest.approx([162.2389, 161.0042, 155.9947, 157.0001, 152.9981], abs=0.002)


def test_node_context_change_closes_ai_fix_and_preserves_instruction():
    activation = _function("activateEditTarget")
    navigation = _function("scrollToNode")
    closer = _function("closeExpandedParagraphAiFix")
    context_change = _function("handleEditorNodeContextChange")
    preview_target = _function("setActivePreviewTarget")
    paragraph_fix = _function("buildParagraphAiFix")

    assert "handleEditorNodeContextChange(nextNodeId)" in activation
    assert "handleEditorNodeContextChange(nodeId)" in preview_target
    assert "activateEditTarget({kind:'node',nodeId:id},{focus:false})" in navigation
    assert "panel.hidden=true" in closer
    assert "editorActions.hidden=false" in paragraph_fix
    assert "expandedParagraphAiFixTarget={nodeId:n.id,blockId:b.id}" in paragraph_fix
    assert "b.revision_instruction=''" not in closer
    assert "b.revision_instruction=''" not in activation

    source = f"""
const instruction={{revision_instruction:'より簡潔に記載する'}};
const panel={{hidden:false}};
const actions={{hidden:true}};
const row={{classList:{{remove:()=>{{}}}},querySelector:()=>actions}};
const document={{querySelectorAll:selector=>selector.includes('.aifix-panel')?[panel]:[row]}};
let expandedParagraphAiFixTarget={{nodeId:'A',blockId:'p1'}};
{closer}
{context_change}
const snapshots=[];
handleEditorNodeContextChange('A');
snapshots.push({{sameHidden:panel.hidden,sameTarget:expandedParagraphAiFixTarget&&expandedParagraphAiFixTarget.nodeId}});
handleEditorNodeContextChange('B');
snapshots.push({{hidden:panel.hidden,target:expandedParagraphAiFixTarget,instruction:instruction.revision_instruction}});
handleEditorNodeContextChange('A');
snapshots.push({{returnedHidden:panel.hidden,returnedTarget:expandedParagraphAiFixTarget,instruction:instruction.revision_instruction}});
console.log(JSON.stringify(snapshots));
"""
    snapshots = _run_node(source)
    assert snapshots[0] == {"sameHidden": False, "sameTarget": "A"}
    assert snapshots[1] == {"hidden": True, "target": None, "instruction": "より簡潔に記載する"}
    assert snapshots[2] == {"returnedHidden": True, "returnedTarget": None, "instruction": "より簡潔に記載する"}


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


def test_step3_textareas_share_non_shrinking_auto_grow_behavior():
    helper = _function("ensureTextareaHeight")
    assert "textarea.style.height='auto'" in helper
    assert "requiredHeight>currentHeight" in helper
    assert "textarea.style.height='32px'" not in helper

    block_builder = _function("buildBlock")
    paragraph_fix = _function("buildParagraphAiFix")
    activation = _function("activateEditTarget")
    assert "ci-input paragraph-textarea" in block_builder
    assert "ensureTextareaHeight(ta)" in block_builder
    assert "document.createElement('textarea')" in paragraph_fix
    assert "aifix-instruction" in paragraph_fix
    assert "ensureTextareaHeight(inp)" in paragraph_fix
    assert "ensureTextareaHeight(inp,true)" in paragraph_fix
    assert "ensureTextareaHeight(targetElement.querySelector('.paragraph-textarea'),true)" in activation

    assert ".paragraph-editor .ci-input{flex:1;min-width:0;min-height:36px" in HTML
    assert "resize:vertical;overflow-x:hidden;overflow-y:auto" in HTML
    assert ".paragraph-aifix .aifix-panel{display:flex;align-items:flex-start" in HTML


def test_textarea_auto_grow_only_increases_height_after_initial_fit():
    helper = _function("ensureTextareaHeight")
    source = f"""
{helper}
const textarea={{
  style:{{height:'120px'}}, offsetHeight:120, clientHeight:118, scrollHeight:70,
  getBoundingClientRect:()=>({{height:Number.parseFloat(textarea.style.height)||120}})
}};
ensureTextareaHeight(textarea);
const manuallyEnlarged=textarea.style.height;
textarea.scrollHeight=150;
ensureTextareaHeight(textarea);
const grown=textarea.style.height;
textarea.scrollHeight=40;
ensureTextareaHeight(textarea);
console.log(JSON.stringify({{manuallyEnlarged,grown,afterShortContent:textarea.style.height}}));
"""
    assert _run_node(source) == {
        "manuallyEnlarged": "120px",
        "grown": "152px",
        "afterShortContent": "152px",
    }
