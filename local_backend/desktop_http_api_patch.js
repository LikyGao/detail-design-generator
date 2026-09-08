(() => {
  'use strict';

  const PREVIEW_STATE_URL = '/api/preview-state';
  const MAIN_CLOSED_SENTINEL = '__DDG_MAIN_WINDOW_CLOSED__';

  const call = async (url, payload) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload === undefined ? undefined : JSON.stringify(payload)
    });
    const text = await response.text();
    let body = {};
    if (text) {
      try { body = JSON.parse(text); }
      catch (_error) { throw new Error(`HTTP ${response.status}`); }
    }
    if (!response.ok) {
      throw new Error(body.detail || body.error || body.message || `HTTP ${response.status}`);
    }
    return body;
  };

  const httpApi = {
    open_preview_window: () => call('/api/desktop/preview/open'),
    save_staged_file: async (token, suggestedName, fileKind, saveAs = false) => {
      const result = await call('/api/desktop/file/save', {
        token,
        suggested_name: suggestedName,
        file_kind: fileKind,
        save_as: !!saveAs
      });
      if (result?.saved && result?.path) result.filename = result.path;
      return result;
    },
    open_project_file: () => call('/api/desktop/project/open'),
    clear_current_project_path: () => call('/api/desktop/project/clear-path')
  };

  const isDetachedPreviewOpen = () =>
    document.getElementById('appShell')?.classList.contains('ddg-detached-preview') === true;

  const pushDetachedPreviewTarget = () => {
    if (!isDetachedPreviewOpen() || typeof currentPreviewState !== 'function') return;
    try {
      const state = currentPreviewState();
      fetch(PREVIEW_STATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state),
        cache: 'no-store'
      }).catch(error => console.warn('[local desktop] preview target sync failed', error));
    } catch (error) {
      console.warn('[local desktop] preview target state failed', error);
    }
  };

  const installPreviewTargetBridge = () => {
    if (window.__ddgPreviewTargetHttpPatched) return;
    if (typeof publishPreviewTarget !== 'function') return;
    const originalPublishPreviewTarget = publishPreviewTarget;
    publishPreviewTarget = function desktopHttpPublishPreviewTarget(...args) {
      const result = originalPublishPreviewTarget.apply(this, args);
      pushDetachedPreviewTarget();
      return result;
    };
    window.__ddgPreviewTargetHttpPatched = true;
  };

  let mainCloseSent = false;
  const notifyDetachedPreviewMainClosed = () => {
    if (mainCloseSent || !isDetachedPreviewOpen()) return;
    mainCloseSent = true;
    let state = {
      html: '', css: '', revision: Date.now(), nodeId: MAIN_CLOSED_SENTINEL,
      blockId: null, updatedAt: Date.now()
    };
    try {
      if (typeof currentPreviewState === 'function') {
        state = { ...currentPreviewState(), nodeId: MAIN_CLOSED_SENTINEL, blockId: null, updatedAt: Date.now() };
      }
    } catch (_error) {
      // The close signal is more important than preserving the final preview payload.
    }
    const body = JSON.stringify(state);
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(PREVIEW_STATE_URL, new Blob([body], { type: 'application/json' }));
        return;
      }
    } catch (_error) {
      // Fall through to keepalive fetch.
    }
    try {
      fetch(PREVIEW_STATE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true
      });
    } catch (_error) {
      // The window is already closing; there is nothing else to surface here.
    }
  };

  const install = () => {
    try {
      const root = window.pywebview || {};
      const api = root.api || {};
      for (const [name, fn] of Object.entries(httpApi)) api[name] = fn;
      root.api = api;
      window.pywebview = root;
      installPreviewTargetBridge();
      document.documentElement.dataset.desktopHttpApi = 'ready';
    } catch (error) {
      console.warn('[local desktop] HTTP desktop API compatibility install failed', error);
    }
  };

  install();
  window.addEventListener('pywebviewready', install);
  window.addEventListener('pagehide', notifyDetachedPreviewMainClosed);
  window.addEventListener('beforeunload', notifyDetachedPreviewMainClosed);
  setTimeout(install, 250);
  setTimeout(install, 1000);
})();
