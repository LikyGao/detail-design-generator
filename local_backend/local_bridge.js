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

  // Keep the company Dify calls untouched. Only the old personal-Dify template
  // lookup is diverted to the local backend.
  const originalDifyCall = window.difyCall;
  if (typeof originalDifyCall === 'function') {
    window.difyCall = async function localAwareDifyCall(apiKey, inputs, apiUrl, returnOutputs = false) {
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
  } else {
    console.error('[local desktop] difyCall was not found; template routing could not be installed.');
  }

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

  // Replace only the standard-template Word workflow. The payload is kept the
  // same as the existing UI data model and is sent directly to the local API.
  window.exportDocx = async function exportDocxLocalBackend() {
    const btn = document.getElementById('exportBtn');
    const old = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> 標準Word生成中...';
    }

    try {
      if (typeof window.renumber === 'function') window.renumber();
      const cover = window.doc?.cover || {};
      const todayText = typeof window.localTodaySlash === 'function' ? window.localTodaySlash() : '';
      const outputFilename = typeof window.canonicalWordOutputFilename === 'function'
        ? window.canonicalWordOutputFilename(cover)
        : '基本設計書.docx';

      cover.file_name = outputFilename;
      if (window.COVER_IDS?.file_name) {
        const fileNameInput = document.getElementById(window.COVER_IDS.file_name);
        if (fileNameInput) fileNameInput.value = outputFilename;
      }

      const revisionHistory = Array.isArray(window.doc?.revision_history)
        ? window.doc.revision_history
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
          document_type: window.doc?.document_type || '',
          client_name: cover.client_name || '',
          project_name: cover.project_name || '',
          version: cover.version || '1.0',
          issue_date: cover.issue_date || '',
          project_no: cover.project_no || '-',
          revision_history_json: revisionHistory,
          chapters_json: window.doc?.chapters || [],
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
      if (typeof window.showToast === 'function') {
        window.showToast('✓ 標準テンプレートからWordファイルを出力しました');
      }
    } catch (error) {
      console.error('[local desktop] Word export failed:', error);
      if (typeof window.showToast === 'function') {
        window.showToast('Word 出力に失敗：' + (error?.message || error), true);
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = old;
      }
    }
  };

  document.documentElement.dataset.localDesktopBridge = 'v1';
})();
