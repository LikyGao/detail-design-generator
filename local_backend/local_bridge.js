(() => {
  'use strict';

  const LOCAL_TEMPLATE_URL = '/api/template-data';
  const LOCAL_TEMPLATE_REGISTER_URL = '/api/templates/register';
  const LOCAL_WORD_URL = '/api/generate-word';
  const LOCAL_WORD_STAGE_URL = '/api/generate-word/stage';
  const LOCAL_PROJECT_STAGE_URL = '/api/project/stage';
  const LOCAL_PREVIEW_STATE_URL = '/api/preview-state';
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

  let desktopApiPromise = null;
  const getDesktopApi = () => {
    if (window.pywebview?.api) return Promise.resolve(window.pywebview.api);
    if (desktopApiPromise) return desktopApiPromise;
    desktopApiPromise = new Promise(resolve => {
      const ready = () => resolve(window.pywebview?.api || null);
      window.addEventListener('pywebviewready', ready, { once: true });
      setTimeout(ready, 3000);
    });
    return desktopApiPromise;
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

  const buildWordRequest = () => {
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
    return {
      outputFilename,
      payload: {
        document_type: doc.document_type || '',
        client_name: cover.client_name || '',
        project_name: cover.project_name || '',
        version: cover.version || '1.0',
        issue_date: cover.issue_date || '',
        project_no: cover.project_no || '-',
        revision_history_json: revisionHistory,
        chapters_json: doc.chapters || [],
        output_filename: outputFilename
      }
    };
  };

  // Standard-template Word generation stays local. In the desktop app the
  // generated file is staged on localhost and then saved with the native
  // Windows Save As dialog, so users always choose the destination explicitly.
  exportDocx = async function exportDocxLocalBackend() {
    const btn = document.getElementById('exportBtn');
    const old = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> 標準Word生成中...';
    }

    try {
      const { outputFilename, payload } = buildWordRequest();
      const api = await getDesktopApi();

      if (api?.save_staged_file) {
        const stagedResponse = await fetch(LOCAL_WORD_STAGE_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const staged = await parseJsonResponse(stagedResponse, 'ローカルWord生成API');
        const result = await api.save_staged_file(staged.token, staged.filename || outputFilename, 'word', true);
        if (result?.cancelled) {
          showToast('Word 出力をキャンセルしました');
          return;
        }
        if (!result?.saved) throw new Error(result?.error || 'Wordファイルを保存できませんでした');
        showToast('✓ Wordファイルを保存しました：' + (result.filename || outputFilename));
        return;
      }

      // Defensive fallback for development in a normal browser.
      const response = await fetch(LOCAL_WORD_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
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

  /* ── Detached dual-monitor preview ─────────────────────────────── */
  let detachedPreviewOpen = false;
  let previewSyncTimer = null;
  let pendingPreviewState = null;
  let previewCssCache = '';

  const installDesktopPreviewStyles = () => {
    if (document.getElementById('ddgDesktopPreviewStyles')) return;
    const style = document.createElement('style');
    style.id = 'ddgDesktopPreviewStyles';
    style.textContent = `
      .app-shell.preview-open.ddg-detached-preview{grid-template-columns:240px 1fr;grid-template-areas:"hd hd" "sb mn"}
      .app-shell.preview-open.ddg-detached-preview #previewArea{display:flex!important;position:fixed!important;left:-12000px!important;top:0!important;width:1000px!important;height:900px!important;visibility:hidden!important;pointer-events:none!important;z-index:-1!important}
      @media(max-width:900px){.app-shell.preview-open.ddg-detached-preview{grid-template-columns:185px 1fr;grid-template-areas:"hd hd" "sb mn"}}
      @media(max-width:680px){.app-shell.preview-open.ddg-detached-preview{grid-template-columns:160px 1fr;grid-template-areas:"hd hd" "sb mn"}}
    `;
    document.head.appendChild(style);
  };

  const collectPreviewCss = () =>
    Array.from(document.querySelectorAll('style'))
      .filter(style => style.id !== 'ddgDesktopPreviewStyles')
      .map(style => style.textContent)
      .join('\n');

  const flushDetachedPreviewState = async () => {
    previewSyncTimer = null;
    const state = pendingPreviewState;
    pendingPreviewState = null;
    if (!state || !detachedPreviewOpen) return;
    try {
      await fetch(LOCAL_PREVIEW_STATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
      });
    } catch (error) {
      console.warn('[local desktop] preview sync failed', error);
    }
  };

  const syncDetachedPreviewState = (state, includeCss = false) => {
    if (!detachedPreviewOpen && !includeCss) return;
    pendingPreviewState = {
      html: state?.html || document.getElementById('previewContent')?.innerHTML || '',
      css: includeCss ? (previewCssCache || collectPreviewCss()) : '',
      revision: Number(state?.revision || Date.now()),
      nodeId: state?.nodeId ?? null,
      blockId: state?.blockId ?? null,
      updatedAt: Number(state?.updatedAt || Date.now())
    };
    clearTimeout(previewSyncTimer);
    previewSyncTimer = setTimeout(flushDetachedPreviewState, includeCss ? 0 : 80);
  };

  const originalPublishPreviewState = publishPreviewState;
  publishPreviewState = function desktopAwarePublishPreviewState() {
    if (detachedPreviewOpen) {
      syncDetachedPreviewState(currentPreviewState(), false);
      return;
    }
    return originalPublishPreviewState();
  };

  const originalTogglePreview = togglePreview;
  togglePreview = function desktopAwareTogglePreview() {
    if (detachedPreviewOpen) {
      getDesktopApi().then(api => api?.open_preview_window?.());
      return;
    }
    return originalTogglePreview();
  };

  openPreviewWindow = async function openDesktopPreviewWindow() {
    try {
      installDesktopPreviewStyles();
      if (!_previewOpen) originalTogglePreview();
      buildPreview();
      previewCssCache = collectPreviewCss();
      detachedPreviewOpen = true;
      document.getElementById('appShell')?.classList.add('ddg-detached-preview');
      const toggleButton = document.getElementById('previewToggleBtn');
      if (toggleButton) {
        toggleButton.dataset.ddgOriginalText = toggleButton.dataset.ddgOriginalText || toggleButton.textContent;
        toggleButton.textContent = '👁 プレビュー（別画面）';
      }
      syncDetachedPreviewState(currentPreviewState(), true);
      await flushDetachedPreviewState();

      const api = await getDesktopApi();
      if (!api?.open_preview_window) throw new Error('デスクトッププレビューAPIを利用できません');
      const result = await api.open_preview_window();
      if (!result?.opened) throw new Error(result?.error || 'プレビューウィンドウを開けませんでした');
      showToast(result.existing ? 'プレビューウィンドウを前面に表示しました' : '✓ プレビューを別ウィンドウで開きました');
    } catch (error) {
      detachedPreviewOpen = false;
      document.getElementById('appShell')?.classList.remove('ddg-detached-preview');
      const toggleButton = document.getElementById('previewToggleBtn');
      if (toggleButton?.dataset.ddgOriginalText) toggleButton.textContent = toggleButton.dataset.ddgOriginalText;
      console.error('[local desktop] detached preview failed:', error);
      showToast('別ウィンドウのプレビューを開けません：' + (error?.message || error), true);
    }
  };

  window.__ddgDesktopPreviewClosed = () => {
    detachedPreviewOpen = false;
    clearTimeout(previewSyncTimer);
    pendingPreviewState = null;
    const shell = document.getElementById('appShell');
    shell?.classList.remove('ddg-detached-preview');
    const toggleButton = document.getElementById('previewToggleBtn');
    if (toggleButton?.dataset.ddgOriginalText) toggleButton.textContent = toggleButton.dataset.ddgOriginalText;
    if (_previewOpen) {
      buildPreview();
      schedulePreviewScale();
    }
    showToast('プレビューをメインウィンドウに戻しました');
  };

  /* ── Project save / Save As / Open (.ddgproj) ────────────────── */
  const sanitizeFileStem = value =>
    String(value || '案件')
      .replace(/[\\/:*?"<>|]/g, '_')
      .replace(/[. ]+$/g, '')
      .trim()
      .slice(0, 80) || '案件';

  const currentPlanValues = () => {
    try {
      return typeof getPlanValues === 'function' ? getPlanValues() : {};
    } catch (_error) {
      return {};
    }
  };

  const captureProjectSnapshot = () => {
    const planValues = currentPlanValues();
    if (phase === PHASE.INPUT && Object.keys(planValues).length) {
      try {
        doc.document_plan = doc.document_plan || {};
        doc.document_plan.summary = assemblePlanText(planValues);
        if (planValues.client) doc.cover.client_name = planValues.client;
        if (planValues.project) doc.cover.project_name = planValues.project;
      } catch (_error) {
        // The document object itself is still serialized below.
      }
    }
    return {
      format: 'detail-design-generator-project',
      schema_version: 1,
      saved_at: new Date().toISOString(),
      phase,
      app_started: !document.getElementById('appShell')?.hidden,
      plan_values: planValues,
      doc: JSON.parse(JSON.stringify(doc))
    };
  };

  const suggestedProjectFilename = () => {
    const name = doc?.cover?.project_name || currentPlanValues()?.project || '案件';
    return sanitizeFileStem(name) + '.ddgproj';
  };

  const saveProject = async (saveAs = false) => {
    try {
      const api = await getDesktopApi();
      if (!api?.save_staged_file) throw new Error('デスクトップ保存APIを利用できません');
      const suggestedName = suggestedProjectFilename();
      const stageResponse = await fetch(LOCAL_PROJECT_STAGE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: captureProjectSnapshot(), suggested_name: suggestedName })
      });
      const staged = await parseJsonResponse(stageResponse, '案件保存API');
      const result = await api.save_staged_file(staged.token, staged.filename || suggestedName, 'project', !!saveAs);
      if (result?.cancelled) return;
      if (!result?.saved) throw new Error(result?.error || '案件を保存できませんでした');
      showToast('✓ 案件を保存しました：' + (result.filename || suggestedName));
    } catch (error) {
      console.error('[local desktop] project save failed:', error);
      showToast('案件の保存に失敗：' + (error?.message || error), true);
    }
  };

  const applyProjectSnapshot = project => {
    if (!project || project.format !== 'detail-design-generator-project' || !project.doc) {
      throw new Error('対応していない案件ファイルです');
    }
    doc = project.doc;
    const requestedPhase = Object.values(PHASE).includes(project.phase) ? project.phase : PHASE.INPUT;
    phase = requestedPhase;

    renderDocumentProfileOptions();
    const landing = document.getElementById('documentLanding');
    const shell = document.getElementById('appShell');
    const started = project.app_started !== false && !!doc.document_type;
    if (landing) landing.hidden = started;
    if (shell) shell.hidden = !started;

    if (!started) {
      updateDocumentTypeDisplay();
      return;
    }

    buildPlanForm();
    if (project.plan_values && typeof fillPlanForm === 'function') fillPlanForm(project.plan_values);
    updateDocumentTypeDisplay();
    setPhase(requestedPhase);

    if (requestedPhase === PHASE.CHAPTERS) {
      renumber();
      renderNav();
      renderChapterSelector();
    } else if (requestedPhase === PHASE.EDIT) {
      renumber();
      bindCover();
      fillCoverInputs();
      renderNav();
      renderEditor();
      renderMissing();
      if (_previewOpen) buildPreview();
    } else {
      renderNav();
    }
    if (typeof resetHistory === 'function') resetHistory();
  };

  const openProject = async () => {
    try {
      const api = await getDesktopApi();
      if (!api?.open_project_file) throw new Error('デスクトップ読込APIを利用できません');
      const selected = await api.open_project_file();
      if (selected?.cancelled) return;
      if (!selected?.opened) throw new Error(selected?.error || '案件ファイルを開けませんでした');
      const response = await fetch(`/api/project/staged/${encodeURIComponent(selected.token)}`, { cache: 'no-store' });
      const project = await parseJsonResponse(response, '案件読込API');
      applyProjectSnapshot(project);
      showToast('✓ 案件を開きました：' + (selected.filename || ''));
    } catch (error) {
      console.error('[local desktop] project open failed:', error);
      showToast('案件を開けません：' + (error?.message || error), true);
    }
  };

  const installProjectButtons = () => {
    const header = document.querySelector('#appShell header');
    const undoButton = document.getElementById('undoBtn');
    if (header && undoButton && !document.getElementById('ddgProjectOpenBtn')) {
      const openButton = document.createElement('button');
      openButton.type = 'button';
      openButton.id = 'ddgProjectOpenBtn';
      openButton.className = 'ebtn ghost';
      openButton.textContent = '開く';
      openButton.title = '保存した案件（.ddgproj）を開く';
      openButton.addEventListener('click', openProject);

      const saveButton = document.createElement('button');
      saveButton.type = 'button';
      saveButton.id = 'ddgProjectSaveBtn';
      saveButton.className = 'ebtn ghost';
      saveButton.textContent = '保存';
      saveButton.title = '案件を保存（Ctrl+S）';
      saveButton.addEventListener('click', () => saveProject(false));

      const saveAsButton = document.createElement('button');
      saveAsButton.type = 'button';
      saveAsButton.id = 'ddgProjectSaveAsBtn';
      saveAsButton.className = 'ebtn ghost';
      saveAsButton.textContent = '別名保存';
      saveAsButton.title = '名前を付けて保存（Ctrl+Shift+S）';
      saveAsButton.addEventListener('click', () => saveProject(true));

      header.insertBefore(openButton, undoButton);
      header.insertBefore(saveButton, undoButton);
      header.insertBefore(saveAsButton, undoButton);
    }

    const landingActions = document.querySelector('.document-type-actions');
    const startButton = document.getElementById('documentTypeStartBtn');
    if (landingActions && startButton && !document.getElementById('ddgLandingOpenProjectBtn')) {
      const button = document.createElement('button');
      button.type = 'button';
      button.id = 'ddgLandingOpenProjectBtn';
      button.className = 'ebtn ghost';
      button.textContent = '案件を開く';
      button.addEventListener('click', openProject);
      landingActions.insertBefore(button, startButton);
    }
  };

  document.addEventListener('keydown', event => {
    if (!(event.ctrlKey || event.metaKey) || String(event.key).toLowerCase() !== 's') return;
    if (document.getElementById('appShell')?.hidden) return;
    event.preventDefault();
    saveProject(!!event.shiftKey);
  });

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
      .ddg-local-template-status{min-height:42px;border:1px solid var(--border);border-radius:4px;background:var(--surface2);padding:9px 10px;font-size:12px;line-height:1.6;color:var(--text-secondary);white-space:pre-line}
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

  installDesktopPreviewStyles();
  installProjectButtons();
  installTemplateManagerButtons();
  document.documentElement.dataset.localDesktopBridge = 'v3';
})();
