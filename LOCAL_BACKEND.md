# Local Backend

## Architecture

```text
基本設計書generator.html
├─ Company Dify: chapter confirmation, body generation and AI correction
└─ Local Backend: template registration/data and DOCX generation
```

Personal Dify was removed from the runtime path to make templates and generated documents local. The legacy workflows and plugin sources remain as references. The backend directly reuses the plugin's chapter parser, template store, and DOCX builder; it does not use the Dify Plugin SDK or an LLM.

## Run locally

```bash
python -m pip install -r local_backend/requirements.txt
python run_local.py
```

The launcher starts `127.0.0.1:8765` and opens the page. Persistent data is stored under `~/.detail-design-generator/data/<document_type>/`. Set `DETAIL_DESIGN_DATA_DIR` to override it.

## API

* `GET /` serves the editor.
* `GET /api/health` reports readiness.
* `POST /api/templates/register` accepts multipart fields `document_type`, `template_file`, and optional `template_version`.
* `POST /api/template-data` accepts `{"document_type":"server_storage"}`.
* `POST /api/generate-word` accepts the existing Word workflow fields and returns a DOCX attachment.

Supported document types are `server_storage`, `network`, `cloud`, and `full`. Register a standard DOCX before requesting its data or generating a document. For example:

```bash
curl -F document_type=server_storage -F template_version=1.0 \
  -F template_file=@standard.docx http://127.0.0.1:8765/api/templates/register
```

## Test and package

```bash
pytest -q
pyinstaller --noconfirm 基本設計書生成ツール.spec
```

The executable is written to `dist/基本設計書生成ツール.exe`. The Windows GitHub Actions workflow runs tests, builds it, and uploads `基本設計書生成ツール-Windows.zip` as the `基本設計書生成ツール-Windows` artifact.

## Troubleshooting

If the editor says `ローカルサービスに接続できません`, start `run_local.py` (or the packaged EXE), ensure port 8765 is free, and check `http://127.0.0.1:8765/api/health`. A template-not-registered response means that the selected document type must be registered through the multipart endpoint first. Company Dify access still requires the existing corporate network/API configuration.
