/* ============================================================
   VikiAgentStore — marketplace app
   ============================================================ */
(function () {
  'use strict';

  var GH = 'https://github.com/A-VigneshRamamoorthy-Code/VikiAgentStore';
  var state = { plugins: [], category: 'All', query: '', sort: 'featured' };
  var els = {};
  var lastFocused = null;

  /* ---------- helpers ---------- */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function icon(name) {
    var p = {
      check: '<path d="M20 6 9 17l-5-5"/>',
      arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
      layers: '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
      book: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22.5z"/><path d="M4 19.5V4.5"/>',
      copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
      copied: '<path d="M20 6 9 17l-5-5"/>',
      tag: '<path d="M20.6 13.4 12 22l-8-8 8.6-8.6A2 2 0 0 1 14 5h6a1 1 0 0 1 1 1v6a2 2 0 0 1-.4 1.4Z"/><circle cx="16.5" cy="7.5" r="1"/>',
      puzzle: '<path d="M8 3a2 2 0 0 1 4 0v1a1 1 0 0 0 1 1h1a2 2 0 1 1 0 4 1 1 0 0 0-1 1v1a2 2 0 1 1-4 0 1 1 0 0 0-1-1H7a2 2 0 1 1 0-4 1 1 0 0 0 1-1z"/>',
      x: '<path d="M18 6 6 18M6 6l12 12"/>',
      ext: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
      down: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>'
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (p[name] || '') + '</svg>';
  }
  function installSnippet(p) {
    return '# 1. Clone the store\n' +
      'git clone ' + GH + '.git\n\n' +
      '# 2. Add the "' + p.name + '" plugin to your agent\n' +
      'cp -r VikiAgentStore/' + p.path + ' ~/.copilot/plugins/';
  }
  function skillCount(p) { return (p.skills && p.skills.length) || 0; }

  /* ---------- rendering: cards ---------- */
  function cardHTML(p, i) {
    var tags = (p.tags || []).slice(0, 3).map(function (t) {
      return '<span class="badge badge-gray badge-pill">' + esc(t) + '</span>';
    }).join('');
    var sc = skillCount(p);
    return '' +
      '<article class="card" role="button" tabindex="0" data-accent="' + esc(p.accent) + '" data-id="' + esc(p.id) + '" style="--i:' + i + '" aria-label="View ' + esc(p.name) + ' plugin details">' +
        '<div class="card-top">' +
          '<div class="card-icon" aria-hidden="true">' + esc(p.icon) + '</div>' +
          '<div class="card-titles">' +
            '<h3>' + esc(p.name) + '</h3>' +
            '<div class="card-author">by ' + esc(p.author) + '</div>' +
          '</div>' +
        '</div>' +
        '<p class="card-desc">' + esc(p.tagline) + ' ' + esc(p.description.split('. ')[1] || '') + '</p>' +
        '<div class="card-tags">' + tags + '</div>' +
        '<div class="card-foot">' +
          '<span class="meta" title="' + sc + ' skill' + (sc === 1 ? '' : 's') + '">' + icon('layers') + sc + ' skill' + (sc === 1 ? '' : 's') + '</span>' +
          '<span class="meta" title="Documentation files">' + icon('book') + (p.docCount || 0) + '</span>' +
          '<span class="grow"></span>' +
          '<span class="card-view">View ' + icon('arrow') + '</span>' +
        '</div>' +
      '</article>';
  }

  function applyFilters() {
    var q = state.query.trim().toLowerCase();
    var list = state.plugins.filter(function (p) {
      if (state.category !== 'All' && p.category !== state.category) return false;
      if (!q) return true;
      var hay = [p.name, p.author, p.tagline, p.description, p.category, (p.tags || []).join(' '),
        (p.skills || []).map(function (s) { return s.name + ' ' + s.description; }).join(' ')].join(' ').toLowerCase();
      return hay.indexOf(q) !== -1;
    });
    if (state.sort === 'name') list.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (state.sort === 'skills') list.sort(function (a, b) { return skillCount(b) - skillCount(a) || a.name.localeCompare(b.name); });
    return list;
  }

  function renderGrid() {
    var list = applyFilters();
    els.grid.innerHTML = list.map(cardHTML).join('');
    var total = state.plugins.length;
    els.empty.classList.toggle('hidden', list.length !== 0);
    els.grid.classList.toggle('hidden', list.length === 0);
    els.resultsMeta.textContent = list.length === total
      ? 'Showing all ' + total + ' plugins'
      : 'Showing ' + list.length + ' of ' + total + ' plugins';
  }

  /* ---------- rendering: chips ---------- */
  function renderChips(categories) {
    els.chips.innerHTML = categories.map(function (c) {
      var on = c === state.category;
      return '<button class="chip" type="button" role="button" aria-pressed="' + on + '" data-cat="' + esc(c) + '">' + esc(c) + '</button>';
    }).join('');
  }

  /* ---------- modal ---------- */
  function modalHTML(p) {
    var skills = (p.skills || []).map(function (s) {
      return '' +
        '<div class="skill-item">' +
          '<div class="s-mark" aria-hidden="true">' + icon('puzzle') + '</div>' +
          '<div>' +
            '<h4>' + esc(s.name) + '</h4>' +
            '<div class="s-author">by ' + esc(s.author) + '</div>' +
            '<p>' + esc(s.description) + '</p>' +
          '</div>' +
        '</div>';
    }).join('');
    var highlights = (p.highlights || []).map(function (h) {
      return '<li>' + icon('check') + '<span>' + esc(h) + '</span></li>';
    }).join('');
    var sc = skillCount(p);

    return '' +
      '<div class="modal-header">' +
        '<div class="card-icon" data-accent-inherit aria-hidden="true">' + esc(p.icon) + '</div>' +
        '<div class="mh-titles">' +
          '<h2 id="modal-title">' + esc(p.name) + '</h2>' +
          '<div class="mh-sub">' +
            '<span class="badge badge-accent badge-pill">' + esc(p.category) + '</span>' +
            '<span class="badge badge-gray">v' + esc(p.version) + '</span>' +
            '<span class="badge badge-success">' + icon('check') + esc(p.license) + '</span>' +
            '<span class="badge">' + icon('layers') + sc + ' skill' + (sc === 1 ? '' : 's') + '</span>' +
          '</div>' +
        '</div>' +
        '<button class="modal-close" id="modal-close" type="button" aria-label="Close dialog">' + icon('x') + '</button>' +
      '</div>' +
      '<div class="modal-body">' +
        '<p class="lead">' + esc(p.description) + '</p>' +
        (highlights ? '<div><div class="block-label">' + icon('check') + 'Highlights</div><ul class="hl-list">' + highlights + '</ul></div>' : '') +
        '<div><div class="block-label">' + icon('layers') + 'What\u2019s inside · ' + sc + ' skill' + (sc === 1 ? '' : 's') + '</div>' + skills + '</div>' +
        '<div><div class="block-label">' + icon('down') + 'Install</div>' +
          '<div class="code-block">' +
            '<button class="copy-btn" id="copy-btn" type="button" aria-label="Copy install commands" title="Copy">' + icon('copy') + '</button>' +
            '<pre><code id="install-code">' + esc(installSnippet(p)) + '</code></pre>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="modal-footer">' +
        '<a class="btn btn-brand" href="' + GH + '/tree/main/' + esc(p.path) + '" target="_blank" rel="noopener">' + icon('ext') + 'View source</a>' +
        '<a class="btn btn-secondary" href="' + GH + '" target="_blank" rel="noopener">' + icon('book') + 'Browse the store</a>' +
      '</div>';
  }

  function openModal(id, pushHash) {
    var p = state.plugins.find(function (x) { return x.id === id; });
    if (!p) return;
    lastFocused = document.activeElement;
    els.modal.setAttribute('data-accent', p.accent);
    els.modal.innerHTML = modalHTML(p);
    els.overlay.hidden = false;
    // next frame → transition in
    requestAnimationFrame(function () { els.overlay.classList.add('open'); });
    document.body.style.overflow = 'hidden';

    $('#modal-close').addEventListener('click', function () { closeModal(true); });
    var copyBtn = $('#copy-btn');
    if (copyBtn) copyBtn.addEventListener('click', function () { copyInstall(copyBtn, p); });

    // focus the close button
    setTimeout(function () { var c = $('#modal-close'); if (c) c.focus(); }, 40);

    if (pushHash !== false && location.hash !== '#plugin/' + id) {
      history.pushState({ plugin: id }, '', '#plugin/' + id);
    }
  }

  function closeModal(updateHash) {
    if (els.overlay.hidden) return;
    els.overlay.classList.remove('open');
    document.body.style.overflow = '';
    setTimeout(function () {
      els.overlay.hidden = true;
      els.modal.innerHTML = '';
    }, 220);
    if (updateHash && /^#plugin\//.test(location.hash)) {
      history.pushState('', '', location.pathname + location.search);
    }
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function copyInstall(btn, p) {
    var text = installSnippet(p);
    var done = function () {
      btn.classList.add('copied');
      btn.innerHTML = icon('copied');
      setTimeout(function () { btn.classList.remove('copied'); btn.innerHTML = icon('copy'); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  }
  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'absolute'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
  }

  /* ---------- focus trap + keyboard ---------- */
  function onKeydown(e) {
    if (els.overlay.hidden) return;
    if (e.key === 'Escape') { closeModal(true); return; }
    if (e.key === 'Tab') {
      var f = els.modal.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])');
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  /* ---------- theme ---------- */
  function currentTheme() {
    var attr = document.documentElement.getAttribute('data-theme');
    if (attr === 'dark' || attr === 'light') return attr;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function syncThemeIcon() {
    var dark = currentTheme() === 'dark';
    $('.i-sun', els.themeToggle).classList.toggle('hidden', dark);
    $('.i-moon', els.themeToggle).classList.toggle('hidden', !dark);
  }
  function toggleTheme() {
    var next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('vas-theme', next); } catch (e) {}
    syncThemeIcon();
  }

  /* ---------- hash routing ---------- */
  function handleHash() {
    var m = location.hash.match(/^#plugin\/(.+)$/);
    if (m) openModal(decodeURIComponent(m[1]), false);
    else closeModal(false);
  }

  /* ---------- stats ---------- */
  function renderStats() {
    var plugins = state.plugins.length;
    var skills = state.plugins.reduce(function (n, p) { return n + skillCount(p); }, 0);
    var docs = state.plugins.reduce(function (n, p) { return n + (p.docCount || 0); }, 0);
    setText('stat-plugins', plugins); setText('stat-skills', skills); setText('stat-docs', docs);
    setText('hero-plugin-count', plugins);
    setText('year', new Date().getFullYear());
  }
  function setText(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  /* ---------- events ---------- */
  function bindEvents(categories) {
    els.search.addEventListener('input', function (e) { state.query = e.target.value; renderGrid(); });
    els.sort.addEventListener('change', function (e) { state.sort = e.target.value; renderGrid(); });

    els.chips.addEventListener('click', function (e) {
      var b = e.target.closest('.chip'); if (!b) return;
      state.category = b.getAttribute('data-cat');
      renderChips(categories); renderGrid();
    });

    els.grid.addEventListener('click', function (e) {
      var c = e.target.closest('.card'); if (!c) return;
      openModal(c.getAttribute('data-id'), true);
    });
    els.grid.addEventListener('keydown', function (e) {
      var c = e.target.closest('.card'); if (!c) return;
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(c.getAttribute('data-id'), true); }
    });

    els.overlay.addEventListener('click', function (e) { if (e.target === els.overlay) closeModal(true); });
    document.addEventListener('keydown', onKeydown);
    els.themeToggle.addEventListener('click', toggleTheme);
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeIcon);
    window.addEventListener('popstate', handleHash);
  }

  /* ---------- boot ---------- */
  function boot(data) {
    state.plugins = data.plugins || [];
    var categories = (data.categories && data.categories.length)
      ? data.categories
      : ['All'].concat(state.plugins.map(function (p) { return p.category; }).filter(function (v, i, a) { return a.indexOf(v) === i; }));

    els = {
      grid: $('#grid'), empty: $('#empty'), chips: $('#chips'),
      search: $('#search'), sort: $('#sort'), resultsMeta: $('#results-meta'),
      overlay: $('#overlay'), modal: $('#modal'), themeToggle: $('#theme-toggle')
    };

    renderStats();
    renderChips(categories);
    renderGrid();
    bindEvents(categories);
    syncThemeIcon();
    handleHash();
  }

  function init() {
    fetch('catalog.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(boot)
      .catch(function (err) {
        console.error('Failed to load catalog:', err);
        var g = document.getElementById('grid');
        if (g) g.innerHTML = '<div class="empty"><h3>Could not load the catalog</h3><p>' + esc(String(err.message || err)) + '</p></div>';
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
