# Standard Word Generator v0.0.13

Dify用の標準Word生成プラグインです。v0.0.7の文書種別別テンプレート管理・章節Master・Word生成を維持し、Heading 1～3配下の通常本文抽出と精確取得を追加します。

v0.0.13では、標準テンプレート本文の`list_group_id`、元のmarker種別、Wordの
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
