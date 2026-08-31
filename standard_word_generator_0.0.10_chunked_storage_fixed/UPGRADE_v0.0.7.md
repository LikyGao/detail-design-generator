# v0.0.7 Upgrade Notes

## Upgrade method

Install `standard_word_generator_0.0.7.difypkg` over v0.0.6. The plugin identity and existing tool names are unchanged, so this is an in-place upgrade rather than a separate plugin.

## Compatibility

- Existing `generate_standard_docx` workflows can continue without new parameters.
- When `document_type` is omitted, selection order is:
  1. registered `full` template
  2. v0.0.6 legacy current template
  3. bundled fallback template
- The first default call after upgrade lazily migrates the v0.0.6 current template into the `full` slot. Legacy keys are retained as a safety fallback.
- Existing registration workflows that only pass `template_file` register it as `full`.

## New template management

Each type retains exactly one current template; registering a new one overwrites that type only.

- `server_storage`
- `network`
- `cloud`
- `full`

The stored data for each type includes:

- raw DOCX
- `template_version`
- tree `master_json`
- flat `chapter_list_json`
- validation and parsing metadata

## New tool

`get_active_template_master` returns both structured variables and JSON text variables for direct use in Dify workflows.

## Chapter IDs

Heading 1–3 are assigned sequential IDs in the existing format:

- `1`
- `1-1`
- `1-1-1`

## Unchanged Word behavior

`docx_builder.py` is unchanged from v0.0.6, including cover/layout preservation, revision history, image/table captions, `SEQ 表`, `SEQ 図`, `STYLEREF`, TOC, table list, and figure list update settings.
