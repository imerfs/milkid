/* Dehyari panel: loads employees / requests / announcements / profile tabs into the dashboard page.
   Every action calls the existing endpoint; the tab is then reloaded so it always shows server state. */
(function () {
  'use strict';
  var csrf = function () { var el = document.querySelector('[name=csrfmiddlewaretoken]'); return el ? el.value : ''; };

  function toast(text, ok) {
    document.querySelectorAll('.mp-toast').forEach(function (old) { old.remove(); });
    var el = document.createElement('div');
    el.className = 'mp-toast ' + (ok ? 'mp-toast-ok' : 'mp-toast-err');
    el.setAttribute('role', 'status');
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 4500);
  }

  function holder(node) { return node.closest('[data-panel]'); }

  function load(pane, url) {
    pane.dataset.current = url;
    return fetch(url, { headers: { 'X-Panel': '1' }, credentials: 'same-origin' })
      .then(function (r) {
        if (r.redirected || !r.ok) { window.location.reload(); throw new Error('redirected'); }   // session or access changed
        return r.text();
      })
      .then(function (html) { pane.innerHTML = html; pane.dataset.loaded = '1'; })
      .catch(function (e) { if (e.message !== 'redirected') pane.innerHTML = '<div class="mp-card mp-empty"><i class="fas fa-triangle-exclamation"></i><p>بارگذاری انجام نشد. دوباره تلاش کنید.</p><button type="button" class="mp-btn" data-mp-reload>تلاش دوباره</button></div>'; });
  }

  function reload(pane) { return load(pane, pane.dataset.current || pane.dataset.panel); }

  function resolve(pane, href) {
    var base = new URL(pane.dataset.current || pane.dataset.panel, window.location.origin);
    return new URL(href, base).toString();
  }

  function send(form, pane) {
    var submit = form.querySelector('[type=submit]');
    if (submit) submit.disabled = true;
    return fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', redirect: 'manual',
        headers: { 'X-Panel': '1', 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {   // a redirect is how the existing views say "done"; do not follow it (it would eat the flash message)
        if (r.type === 'opaqueredirect') return { ok: true, data: null };
        return r.json().catch(function () { return null; }).then(function (d) { return { ok: r.ok, data: d }; });
      })
      .then(function (res) {
        if (!res.ok || (res.data && res.data.success === false)) {
          var d = res.data || {};
          toast((d.errors && d.errors.join(' ')) || d.error || 'عملیات انجام نشد.', false);
          return false;
        }
        var dlg = form.closest('dialog'); if (dlg && form.hasAttribute('data-mp-close')) dlg.close();
        if (form.hasAttribute('data-mp-keep')) {
          toast((res.data && res.data.message) || 'ذخیره شد.', true);
          if (form.hasAttribute('data-mp-reset')) form.reset();
        } else { return reload(pane); }
        return true;
      })
      .catch(function () { toast('ارتباط با سرور برقرار نشد.', false); })
      .finally(function () { if (submit) submit.disabled = false; });
  }

  document.addEventListener('submit', function (e) {
    var form = e.target, pane = holder(form);
    if (!pane) return;
    if (form.hasAttribute('data-mp-get')) {
      e.preventDefault();
      load(pane, resolve(pane, form.getAttribute('action') || '') + (form.getAttribute('action').indexOf('?') < 0 ? '?' : '&') + new URLSearchParams(new FormData(form)).toString());
    } else if (form.hasAttribute('data-mp-post')) {
      e.preventDefault();
      var msg = form.getAttribute('data-confirm');
      if (msg && !window.confirm(msg)) return;
      send(form, pane);
    }
  });

  document.addEventListener('click', function (e) {
    var dock = e.target.closest('a[href$="/mayor/roles/"]');   // the office dock's roles shortcut opens the tab in place
    if (dock && document.querySelector('.sidebar-item[data-page="employees"]')) { e.preventDefault(); window.mpOpen('employees'); return; }
    var t = e.target.closest('[data-mp-url],[data-mp-act],[data-mp-open],[data-mp-dismiss],[data-mp-reload]');
    if (!t) return;
    var pane = holder(t);
    if (!pane) return;
    if (t.hasAttribute('data-mp-url')) { e.preventDefault(); load(pane, resolve(pane, t.getAttribute('href'))); }
    else if (t.hasAttribute('data-mp-reload')) { reload(pane); }
    else if (t.hasAttribute('data-mp-dismiss')) { t.closest('dialog').close(); }
    else if (t.hasAttribute('data-mp-open')) {
      var dlg = document.getElementById(t.getAttribute('data-mp-open'));
      var form = dlg.querySelector('form');
      if (t.dataset.action) form.action = t.dataset.action;
      dlg.showModal();
    } else if (t.hasAttribute('data-mp-act')) {
      var msg = t.getAttribute('data-confirm');
      if (msg && !window.confirm(msg)) return;
      t.disabled = true;
      fetch(t.getAttribute('data-mp-act'), { method: 'POST', credentials: 'same-origin',
          headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (res.ok && res.d.success !== false) return reload(pane);
          toast(res.d.error || 'عملیات انجام نشد.', false); t.disabled = false;
        })
        .catch(function () { toast('ارتباط با سرور برقرار نشد.', false); t.disabled = false; });
    }
  });

  window.mpLoadTab = function (content) {
    if (content && content.dataset.panel && !content.dataset.loaded) load(content, content.dataset.panel);
  };
  window.mpOpen = function (tab) {
    var link = document.querySelector('.sidebar-item[data-page="' + tab + '"]');
    if (link) link.click();
  };
  window.addEventListener('load', function () {   // after the dashboard's own tab handlers are bound
    var tab = new URLSearchParams(window.location.search).get('tab');
    if (tab) window.mpOpen(tab);
  });
})();
