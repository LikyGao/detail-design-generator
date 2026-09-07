(() => {
  'use strict';

  const FULL_TEMPLATE_URL = '/api/template-data';
  const STATUS_URL = '/api/templates/status';
  const originalFetch = window.fetch.bind(window);

  window.fetch = function ddgTemplateManagerAwareFetch(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const manager = document.getElementById('ddgLocalTemplateManager');
    const managerOpen = !!manager && !manager.hidden;

    if (managerOpen && (url === FULL_TEMPLATE_URL || url.endsWith(FULL_TEMPLATE_URL))) {
      return originalFetch(STATUS_URL, init);
    }
    return originalFetch(input, init);
  };

  document.documentElement.dataset.templateManagerStatusPatch = 'v1';
})();
