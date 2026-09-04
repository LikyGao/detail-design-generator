# Standard Word Generator v0.0.24

## Cover filename correction

- Replaces every inline XML node in a cover-property value paragraph before
  inserting its new text. This removes stale field results and prevents the
  visible filename from appearing twice.
- Preserves the paragraph properties and the first run's formatting.

## Dify workflow dependency

`dify/personal/workflows/基本設計書_Word生成API.yml` still identifies packaged plugin
version `0.0.10`. This source tree is version `0.0.24`. The workflow identifier
has deliberately not been edited because a valid Dify package hash cannot be
derived from source. After packaging and installing v0.0.24, reselect that
installed plugin version in the Dify workflow editor and export the workflow.
