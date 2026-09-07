(() => {
  'use strict';

  const LOCAL_TEMPLATE_URL = '/api/template-data';
  const LOCAL_WORD_URL = '/api/generate-word';
  const PERSONAL_DIFY_URL = 'https://api.dify.ai/v1/workflows/run';
  const PERSONAL_TEMPLATE_KEY = 'app-nYF68CJV3Scjj5XdVitHxwRr';

  const parseJsonResponse = async (response, label) => {
    const text = await response.text();
    let body = {};
    if (text) {
      try {
        body = JSON.parse(text);
      } catch (error) {
        console.error(`[local desktop] ${label} returned non-JSON`, response.status, text, error);
        throw new Error(`HTTP ${response.status}：${label}からJSON以外の応答が返されました`);
      }
    }
    if (!response.ok) {
      const message = body.detail || body.message || body.error || `${label} request failed`;
      throw new Error(`HTTP ${response.status}：${message}`);
    }
    return body;
  };

  // The main HTML uses top-level let/const state (for example `doc`), which is
  // shared across classic scripts but is intentionally not attached to window.
  // Therefore the bridge uses the original global bindings directly.
  const originalDifyCall = difyCall;
  difyCall = async function localAwareDifyCall(apiKey, inputs, apiUrl, returnOutputs = false) {
    const isPersonalTemplateCall =
      apiKey === PERSONAL_TEMPLATE_KEY ||
      (apiUrl === PERSONAL_DIFY_URL && inputs && Object.prototype.hasOwnProperty.call(inputs, 'document_type'));

    if (isPersonalTemplateCall) {
      const response = await fetch(LOCAL_TEMPLATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_type: String(inputs?.document_type || '') })
      });
      return parseJsonResponse(response, 'ローカル標準テンプレートAPI');
    }

    return originalDifyCall(apiKey, inputs, apiUrl, returnOutputs);
  };

  const saveBlob = (blob, fileName) => {
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
    }, 1000);
  };

  // Replace only the standard-template Word workflow. Company Dify calls used
  // for chapter judgement / AI editing keep using the existing implementation.
  exportDocx = async function exportDocxLocalBackend() {
    const btn = document.getElementById('exportBtn');
    const old = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> 標準Word生成中...';
    }

    try {
      renumber();
      const cover = doc.cover || {};
      const todayText = localTodaySlash();
      const outputFilename = canonicalWordOutputFilename(cover);

      cover.file_name = outputFilename;
      const fileNameInput = document.getElementById(COVER_IDS.file_name);
      if (fileNameInput) fileNameInput.value = outputFilename;

      const revisionHistory = Array.isArray(doc.revision_history)
        ? doc.revision_history
        : [{
            issue_date: cover.issue_date || todayText,
            version: cover.version || '1.0',
            editor: '',
            description: '新規作成'
          }];

      const response = await fetch(LOCAL_WORD_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_type: doc.document_type || '',
          client_name: cover.client_name || '',
          project_name: cover.project_name || '',
          version: cover.version || '1.0',
          issue_date: cover.issue_date || '',
          project_no: cover.project_no || '-',
          revision_history_json: revisionHistory,
          chapters_json: doc.chapters || [],
          output_filename: outputFilename
        })
      });

      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const errorBody = await response.json();
          message += `：${errorBody.detail || errorBody.message || errorBody.error || 'ローカルWord生成に失敗しました'}`;
        } catch (_error) {
          message += '：ローカルWord生成に失敗しました';
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      if (!blob.size) throw new Error('ローカルWord生成APIから空のファイルが返されました');
      saveBlob(blob, outputFilename);
      showToast('✓ 標準テンプレートからWordファイルを出力しました');
    } catch (error) {
      console.error('[local desktop] Word export failed:', error);
      showToast('Word 出力に失敗：' + (error?.message || error), true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    }
  };

  document.documentElement.dataset.localDesktopBridge = 'v1';
})();
