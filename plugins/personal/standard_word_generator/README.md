# Standard Word Generator v0.0.22

Dify用の標準Word生成プラグインです。v0.0.7の文書種別別テンプレート管理・章節Master・Word生成を維持し、Heading 1～3配下の通常本文抽出と精確取得を追加します。

v0.0.15では、段落自身のWord styleをbasedOn ancestorと分離して保存し、現在styleの
完全一致`pStyle`と`numPr`を先に解決します。現在styleにnumbering定義がない場合だけ、
最も近いbasedOn styleから順にfallbackします。またnative `ilvl 0～5`を
`level_1, level_2, level_4, level_3, level_5, level_6`へ明示的に対応付けます。

Word固有のnumbering情報を可視文字より優先し、`numId`から
`abstractNumId`と`ilvl 0～5`を解決します。numbering levelの`numFmt`、`lvlText`、
`pStyle`、indent、symbol fontと、段落styleの`basedOn`継承チェーンも保存します。
これにより同じ「・」を使う別階層やWingdingsの矢印を圧縮せず、`paragraph_style`の
`level_1`～`level_6`として再生成できます。可視marker判定はnumberingがない場合だけ
fallbackとして使用します。

また、標準テンプレート本文の`list_group_id`、元のmarker種別、Wordの
`numId` / `abstractNumId` / `ilvl` / `startOverride`、および段落indentを保存します。
同一list group内だけを再採番するため、独立した囲み番号列はそれぞれ①から始まり、
「・」と「➢」も再生成時に維持されます。新規段落は隣接する同レベルのgroupを継承します。
明示indentがない場合のみ、標準テンプレート由来のコンパクトなfallbackを使用します。

## 文書種別

- `server_storage`
- `network`
- `cloud`
- `full`

各文書種別には現在のテンプレートを1件保存します。同じ種別へ再登録すると、その種別のDOCX、章節Master、章節本文、版数が上書きされます。

## ツール

- `register_standard_template`
  - DOCXを登録
  - Heading 1～3から`master_json` / `chapter_list_json`を生成
  - 各Heading配下の通常本文段落を保存
  - Word表内テキスト、画像、Caption、Point専用段落は本文抽出対象外
- `get_active_template_master`
  - 指定種別の現在の章節Master、`template_id`、`template_version`を取得
- `get_template_section_texts`
  - 指定した章節IDの標準本文をストレージから精確取得
  - `section_ids_json`はID配列、または`id`を含む章節ツリー/リストを受け付ける
  - 空欄時は全章節を返す
  - 手動追加章節などテンプレートにないIDは`missing_section_ids`へ返す
- `generate_standard_docx`
  - 指定した文書種別のテンプレートからDOCXを生成
  - 任意の`template_id` / `template_version`不一致時はエラーにして誤テンプレート使用を防止
- `get_template_status`
- `download_current_template`

## 互換性

既存ツール名と既存パラメーターを維持しています。v0.0.7で登録済みのテンプレートはMaster取得・Word生成に引き続き利用できますが、章節本文を利用するにはv0.0.8導入後に標準テンプレートを再登録してください。

## 0.0.22

通常のnative Word style段落では、paragraph-local `w:numPr`を書き込まず、`pStyle`と
テンプレートの`styles.xml` / `numbering.xml`にnumberingとindentを委ねるようにしました。
Wordで同じstyleを再適用した場合と同じ段落プロパティになり、浅い「・」、深い「・」、
①、➢の各style固有の配置を維持します。独立した番号グループまたは章節単位の番号restartが
必要な番号styleに限り、native `ilvl`を保った新しいnum instanceと`startOverride`を設定します。

## 0.0.21

Native Word list styleで生成する段落には`numPr`だけを設定し、段落ローカルの
`w:ind`を生成しないようにしました。これにより同じ「・」を使う浅い階層と深い階層も、
各style / native `ilvl`に対応する`numbering.xml`本来のindentで表示されます。

## 0.0.20

Resets ungrouped child numbering when a level-1 paragraph begins a new hierarchy, including when level 1 uses its synthetic per-node scope, while preserving counters for explicit independent child list groups.

## 0.0.19

Restarts level-1 native numbering for every chapter/section node and restores native paragraph indentation from the template numbering level, so paragraph/style-local zero indentation cannot override the canonical list geometry.

## 0.0.18

Restores template-canonical effective indentation explicitly on newly generated native-numbered paragraphs, preserving distinct shallow/deep bullet and circled-number layouts while retaining automatic Word numbering.

## 0.0.17

Preserves native paragraph-style, numbering, hierarchy, indent, and list-group metadata end to end. Parsing is style-first (including locally cancelled numbering), and generation dynamically reuses template-native styles and automatic numbering with independent list restarts. Literal-marker generation remains only as a fallback when no native descriptor exists.

## 0.0.17

Preserves native paragraph-style, numbering, hierarchy, indent, and list-group metadata end to end. Parsing is style-first (including locally cancelled numbering), and generation dynamically reuses template-native styles and automatic numbering with independent list restarts. Literal-marker generation remains only as a fallback when no native descriptor exists.
