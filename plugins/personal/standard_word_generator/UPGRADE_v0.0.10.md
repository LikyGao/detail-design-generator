# v0.0.10

- Large DOCX and section-content payloads are stored in 256 KiB KV chunks.
- Existing unchunked templates remain readable.
- Full template with 14 Heading 1 chapters is supported without special limits.
- Storage failures now identify the exact key/chunk.
