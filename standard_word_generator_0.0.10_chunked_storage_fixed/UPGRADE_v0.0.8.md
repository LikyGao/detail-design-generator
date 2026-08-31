# v0.0.8 Upgrade Notes

## 追加内容

- Heading 1～3配下の通常本文を章節単位で抽出・保存
- 新ツール`get_template_section_texts`
- `register_standard_template`と`get_active_template_master`のトップレベル出力へ`template_id`を追加
- `generate_standard_docx`へ任意の`template_id`検証を追加

## 抽出対象

抽出するもの:

- 文書本文のHeading 1～3
- 各Headingの後ろに続く通常段落
- 箇条書き・番号付き段落の構造情報

抽出しないもの:

- Word表内の文字
- 画像
- Caption段落
- Point専用段落

## 導入後の操作

v0.0.7で登録済みの各標準テンプレートは、v0.0.8導入後に標準テンプレート管理ワークフローから再登録してください。再登録すると章節本文データが保存されます。
