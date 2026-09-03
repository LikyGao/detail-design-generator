# Word metadata passthrough deployment update

The existing company Dify app workflow `②本文生成_v4_標準本文読込` was updated in place. Import this YAML or replace the code in the **生成入力・標準本文解析** node with the repository version. Its paragraph normalization now copies the complete input object and only normalizes `type`, `paragraph_style`, and `text`; unknown native Word metadata therefore remains opaque and intact. The standard-text merge node already uses the same copy-and-normalize pattern, and the paragraph-revision path returns only revised `text`, so the client merges text without replacing the source block.

Keep the existing app and API key. Do not create a new app. Publish the workflow again after updating the Code node. Git changes do not update a deployed Dify workflow automatically.

The personal Word-generation workflow continues to pass `start.chapters_json` directly to `generate_standard_docx`; when deploying plugin 0.0.17, rebind/install the actual packaged plugin in Dify without inventing or editing a `plugin_unique_identifier` hash. The template-data API continues to return stored `section_contents_json` without rebuilding paragraph dictionaries.
