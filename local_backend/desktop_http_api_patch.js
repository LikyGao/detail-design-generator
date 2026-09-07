(() => {
  'use strict';

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

  const install = () => {
    try {
      const root = window.pywebview || {};
      const api = root.api || {};
      for (const [name, fn] of Object.entries(httpApi)) api[name] = fn;
      root.api = api;
      window.pywebview = root;
      document.documentElement.dataset.desktopHttpApi = 'ready';
    } catch (error) {
      console.warn('[local desktop] HTTP desktop API compatibility install failed', error);
    }
  };

  install();
  window.addEventListener('pywebviewready', install);
  setTimeout(install, 250);
  setTimeout(install, 1000);
})();
