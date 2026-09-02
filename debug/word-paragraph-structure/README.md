# Real Word paragraph structure debug notes

Source template: `基本設計書_分割版サーバー・ストレージ_2.1.docx`

Purpose: investigate why `standard_word_generator` v0.0.13 still fails to identify/preserve smaller paragraph units and nested list levels.

## Important finding from the actual DOCX

The template does **not** rely only on visible literal characters such as `①`, `・`, or `➢`. The native Word numbering definition (`word/numbering.xml`) contains a multi-level list with these levels:

| ilvl | numFmt | lvlText | linked paragraph style | indent | font |
|---|---|---|---|---|---|
| 0 | decimal | `(%1)` | `0` | left 440 / hanging 440 | default |
| 1 | bullet | `・` | `1` | left 340 / hanging 170 | default |
| 2 | decimalEnclosedCircle | `%3` | `2` | left 510 / hanging 226 | default |
| 3 | bullet | `` | `3` | left 510 / hanging 283 | **Wingdings** |
| 4 | bullet | `・` | `4` | left 794 / hanging 624 | Meiryo UI |
| 5 | decimalEnclosedCircle | `%6` | `5` | left 794 / hanging 510 | Meiryo UI |

This means the real hierarchy is encoded by `w:ilvl`, `w:numFmt`, `w:lvlText`, `w:pStyle`, inherited style indent, and symbol font. In particular, the arrow-looking level is stored as Wingdings ``, not necessarily as Unicode `➢` in visible paragraph text.

## Representative real paragraphs

The following paragraphs were extracted from `word/document.xml`:

- DNS heading: style `30`, `numId=2`, `ilvl=2`, direct left indent 227.
- SMTP heading: style `30`, `numId=2`, `ilvl=2`, direct left indent 227.
- `Localhost`: style `3`, `numId=1`, `ilvl=3`, hanging 227.
- `XXXXX.com.local`: style `3`, `numId=1`, `ilvl=3`, hanging 227.
- `スパムアンチ`: style `3`, `numId=1`, `ilvl=3`, hanging 227.
- `POP`: style `3`, `numId=1`, `ilvl=3`, hanging 227.
- `IMAP`: style `3`, `numId=1`, `ilvl=3`, hanging 227.
- `XXX(製品名)`: style `3`, `numId=1`, `ilvl=3`, hanging 227.

The relevant paragraph styles are also hierarchical:

- style `1` (`スタイル1`) based on `a3`, left 510
- style `2` (`スタイル2`) based on `a`, left 794 / hanging 284
- style `3` (`スタイル3`) based on style `2`, left 737 / hanging 227
- style `4` (`スタイル4`) based on style `3`, left 964 / hanging 170
- style `30` is `heading 3`, based on style `20`, left 227

## What Codex should inspect

Compare this real structure with:

`plugins/personal/standard_word_generator/tools/chapter_parser.py`

Do not hard-code paragraph text from this template.

Please determine why v0.0.13 collapses or misclassifies these smaller units. The parser should use native Word semantics first, especially:

- `w:numPr`
- `w:numId`
- `w:ilvl`
- referenced `w:abstractNum`
- `w:numFmt`
- `w:lvlText`
- numbering-level `w:pPr/w:ind`
- paragraph style inheritance
- symbol font (`Wingdings` / other symbol fonts)

Literal character detection should only be a fallback, not the primary source of truth.

## Required work

1. Explain exactly why the current v0.0.13 logic fails on this real template.
2. Modify the parser generically, without hard-coding template text.
3. Add regression tests that represent the real ilvl 0-5 hierarchy above, including the Wingdings arrow level.
4. Bump the plugin version.
5. Verify that after reinstalling the new plugin and re-uploading/re-parsing the standard template, the extracted `paragraph_style` / level preserves the smaller paragraph units correctly.
