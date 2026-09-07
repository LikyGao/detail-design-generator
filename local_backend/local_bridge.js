(() => {
  'use strict';

  const LOCAL_TEMPLATE_URL = '/api/template-data';
  const LOCAL_TEMPLATE_REGISTER_URL = '/api/templates/register';
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

  const documentTypeLabel = {
    server_storage: 'サーバー・ストレージ版',
    network: 'ネットワーク版',
    cloud: 'クラウド版',
    full: '全体版'
  };

  const activeDocumentType = () => {
    if (doc?.document_type) return doc.document_type;
    const checked = document.querySelector('.document-profile input:checked');
    return checked?.value || 'server_storage';
  };

  const installTemplateManagerStyles = () => {
    if (document.getElementById('ddgLocalTemplateStyles')) return;
    const style = document.createElement('style');
    style.id = 'ddgLocalTemplateStyles';
    style.textContent = `
      .ddg-local-template-backdrop{position:fixed;inset:0;z-index:5000;background:rgba(15,23,42,.42);display:flex;align-items:center;justify-content:center;padding:24px}
      .ddg-local-template-backdrop[hidden]{display:none}
      .ddg-local-template-dialog{width:min(560px,calc(100vw - 40px));background:var(--surface);color:var(--text-main);border:1px solid var(--border);border-radius:6px;box-shadow:0 18px 48px rgba(0,0,0,.25);overflow:hidden}
      .ddg-local-template-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--surface2);border-bottom:1px solid var(--border);font-weight:700}
      .ddg-local-template-close{border:1px solid var(--border);background:var(--surface);color:var(--text-main);border-radius:4px;min-width:30px;height:30px;cursor:pointer}
      .ddg-local-template-body{padding:16px;display:flex;flex-direction:column;gap:12px}
      .ddg-local-template-field{display:flex;flex-direction:column;gap:5px}
      .ddg-local-template-field label{font-size:11px;font-weight:600;color:var(--text-label)}
      .ddg-local-template-field select,.ddg-local-template-field input[type=text],.ddg-local-template-field input[type=file]{width:100%;min-height:34px;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--text-main);padding:6px 8px;font:inherit}
      .ddg-local-template-actions{display:flex;gap:8px;justify-content:flex-end;padding-top:4px}
      .ddg-local-template-status{min-height:42px;border:1px solid var(--border);border-radius:4px;background:var(--surface2);padding:9px 10px;font-size:12px;line-height:1.6;color:var(--text-secondary)}
      .ddg-local-template-status.ok{border-color:rgba(25,122,82,.45);color:var(--green)}
      .ddg-local-template-status.error{border-color:rgba(180,35,24,.45);color:var(--red)}
      .ddg-local-template-help{font-size:11px;color:var(--text-muted);line-height:1.6}
    `;
    document.head.appendChild(style);
  };

  const ensureTemplateManager = () => {
    let backdrop = document.getElementById('ddgLocalTemplateManager');
    if (backdrop) return backdrop;

    installTemplateManagerStyles();
    backdrop = document.createElement('div');
    backdrop.id = 'ddgLocalTemplateManager';
    backdrop.className = 'ddg-local-template-backdrop';
    backdrop.hidden = true;
    backdrop.innerHTML = `
      <div class="ddg-local-template-dialog" role="dialog" aria-modal="true" aria-labelledby="ddgLocalTemplateTitle">
        <div class="ddg-local-template-head">
          <span id="ddgLocalTemplateTitle">標準テンプレート管理（ローカル）</span>
          <button type="button" class="ddg-local-template-close" id="ddgLocalTemplateClose" aria-label="閉じる">×</button>
        </div>
        <div class="ddg-local-template-body">
          <div class="ddg-local-template-field">
            <label for="ddgLocalTemplateType">文書種別</label>
            <select id="ddgLocalTemplateType">
              ${Object.entries(documentTypeLabel).map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}
            </select>
          </div>
          <div class="ddg-local-template-status" id="ddgLocalTemplateStatus">登録状態を確認します。</div>
          <div class="ddg-local-template-field">
            <label for="ddgLocalTemplateFile">標準テンプレート（.docx）</label>
            <input id="ddgLocalTemplateFile" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
          </div>
          <div class="ddg-local-template-field">
            <label for="ddgLocalTemplateVersion">テンプレートバージョン（任意）</label>
            <input id="ddgLocalTemplateVersion" type="text" placeholder="例：2.1">
          </div>
          <div class="ddg-local-template-help">登録したテンプレートはこのPC内に保存されます。個人Dify環境には送信されません。</div>
          <div class="ddg-local-template-actions">
            <button type="button" class="ebtn ghost" id="ddgLocalTemplateRefresh">登録状態を更新</button>
            <button type="button" class="ebtn" id="ddgLocalTemplateRegister">登録</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(backdrop);

    const typeSelect = backdrop.querySelector('#ddgLocalTemplateType');
    const status = backdrop.querySelector('#ddgLocalTemplateStatus');
    const fileInput = backdrop.querySelector('#ddgLocalTemplateFile');
    const versionInput = backdrop.querySelector('#ddgLocalTemplateVersion');
    const registerButton = backdrop.querySelector('#ddgLocalTemplateRegister');

    const setStatus = (message, kind = '') => {
      status.textContent = message;
      status.classList.remove('ok', 'error');
      if (kind) status.classList.add(kind);
    };

    const refresh = async () => {
      const type = typeSelect.value;
      setStatus('登録状態を確認しています…');
      try {
        const response = await fetch(LOCAL_TEMPLATE_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ document_type: type })
        });
        if (response.status === 404) {
          setStatus(`${documentTypeLabel[type] || type}：未登録`, 'error');
          return;
        }
        const data = await parseJsonResponse(response, 'ローカル標準テンプレートAPI');
        setStatus(
          `${documentTypeLabel[type] || type}：登録済み\nバージョン ${data.template_version || '-'} / 章節 ${data.returned_section_count ?? '-'} 件`,
          'ok'
        );
      } catch (error) {
        setStatus(error?.message || String(error), 'error');
      }
    };

    const register = async () => {
      const file = fileInput.files?.[0];
      if (!file) {
        setStatus('登録する.docxファイルを選択してください。', 'error');
        return;
      }
      if (!file.name.toLowerCase().endsWith('.docx')) {
        setStatus('登録できるファイルは.docxのみです。', 'error');
        return;
      }
      registerButton.disabled = true;
      setStatus('テンプレートを解析・登録しています…');
      try {
        const form = new FormData();
        form.append('document_type', typeSelect.value);
        form.append('template_version', versionInput.value.trim());
        form.append('template_file', file, file.name);
        const response = await fetch(LOCAL_TEMPLATE_REGISTER_URL, { method: 'POST', body: form });
        const data = await parseJsonResponse(response, 'ローカルテンプレート登録API');
        setStatus(
          `${documentTypeLabel[typeSelect.value] || typeSelect.value}：登録完了\nバージョン ${data.template_version || '-'} / Template ID ${data.template_id || '-'}`,
          'ok'
        );
        fileInput.value = '';
      } catch (error) {
        setStatus(error?.message || String(error), 'error');
      } finally {
        registerButton.disabled = false;
      }
    };

    backdrop.querySelector('#ddgLocalTemplateClose').addEventListener('click', () => { backdrop.hidden = true; });
    backdrop.addEventListener('click', event => { if (event.target === backdrop) backdrop.hidden = true; });
    backdrop.querySelector('#ddgLocalTemplateRefresh').addEventListener('click', refresh);
    registerButton.addEventListener('click', register);
    typeSelect.addEventListener('change', refresh);
    backdrop._ddgRefresh = refresh;
    return backdrop;
  };

  const openTemplateManager = () => {
    const manager = ensureTemplateManager();
    const typeSelect = manager.querySelector('#ddgLocalTemplateType');
    const type = activeDocumentType();
    if (documentTypeLabel[type]) typeSelect.value = type;
    manager.hidden = false;
    manager._ddgRefresh?.();
  };

  const installTemplateManagerButtons = () => {
    const addButton = (container, marker) => {
      if (!container || container.querySelector(`[data-ddg-local-template-button="${marker}"]`)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ebtn ghost';
      button.dataset.ddgLocalTemplateButton = marker;
      button.textContent = 'テンプレート管理';
      button.addEventListener('click', openTemplateManager);
      container.appendChild(button);
    };
    addButton(document.querySelector('.document-type-actions'), 'landing');
    addButton(document.querySelector('#appShell header'), 'header');
  };

  installTemplateManagerButtons();
  document.documentElement.dataset.localDesktopBridge = 'v2';
})();
