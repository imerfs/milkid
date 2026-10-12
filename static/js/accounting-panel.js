/* Accountant workspace: one page, many views. Handles the dialog, toasts, menu state, theme and the command palette around HTMX. */
(function () {
    var dialog = document.getElementById('acc-modal');
    var body = document.getElementById('acc-modal-body');
    var panel = document.getElementById('acc-panel');
    var toast = document.getElementById('acc-toast');
    var side = document.getElementById('ac-side');
    if (!dialog || !body || !panel) return;
    var timer;

    function say(message, bad) {
        toast.textContent = message;
        toast.className = bad ? 'bad' : '';
        clearTimeout(timer);
        timer = setTimeout(function () { toast.className = 'hidden'; }, 4500);
    }
    function reload() {
        htmx.ajax('GET', panel.dataset.url || panel.getAttribute('hx-get'), { target: '#acc-panel', swap: 'innerHTML' });
    }
    function view() { return panel.querySelector('#acc-view'); }
    function openTab(tab, extra) {
        var v = view();
        var year = v && v.dataset.year ? 'year=' + v.dataset.year + '&' : '';
        htmx.ajax('GET', panel.dataset.base + '?' + year + 'tab=' + tab + (extra ? '&' + extra : ''),
                  { target: '#acc-panel', swap: 'innerHTML' });
    }
    function openModal(url) { if (url) htmx.ajax('GET', url, { target: '#acc-modal-body', swap: 'innerHTML' }); }
    function closeSide() { if (side) side.classList.remove('open'); }

    // Remember the page address (tab, filters, page number) so a saved change reloads the same view,
    // and keep the menu and breadcrumb in step with the page that is showing.
    function syncMenu() {
        var v = view();
        if (!v) return;
        document.querySelectorAll('[data-acc-tab]').forEach(function (a) {
            var on = a.dataset.accTab === v.dataset.tab;
            a.classList.toggle('active', on);
            if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
        });
        var crumb = document.getElementById('ac-crumb');
        if (crumb) crumb.textContent = v.dataset.tabLabel || '';
        var active = document.querySelector('.ac-mobnav .active');
        if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest', inline: 'center' });
    }
    document.body.addEventListener('htmx:afterSwap', function (e) {
        if (e.detail.target === panel) {
            panel.dataset.url = e.detail.pathInfo.finalRequestPath;
            syncMenu();
        }
        if (e.detail.target === body && !dialog.open) dialog.showModal();
    });
    // Validation answers (400/409) carry the form again with the error, so swap them into the dialog.
    document.body.addEventListener('htmx:beforeSwap', function (e) {
        var status = e.detail.xhr.status;
        if (e.detail.target === body && (status === 400 || status === 409 || status === 422)) {
            e.detail.shouldSwap = true;
            e.detail.isError = false;
        }
    });
    document.body.addEventListener('accDone', function (e) {
        dialog.close();
        say(e.detail.message || 'انجام شد.');
        reload();
    });
    document.body.addEventListener('accError', function (e) { say(e.detail.message || 'انجام نشد.', true); });
    document.body.addEventListener('htmx:responseError', function (e) {
        if (!e.detail.xhr.getResponseHeader('HX-Trigger')) say('انجام عملیات ممکن نبود. دسترسی یا اتصال را بررسی کنید.', true);
    });
    document.body.addEventListener('htmx:sendError', function () { say('اتصال به سرور برقرار نشد.', true); });

    dialog.addEventListener('click', function (e) {
        // closes on the X / cancel buttons and on a click on the backdrop
        if (e.target.closest('[data-acc-close]') || e.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', function () { body.innerHTML = ''; });

    // Menu links open a page of the workspace (optionally filtered) instead of leaving the page.
    document.querySelectorAll('[data-acc-tab]').forEach(function (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            openTab(link.dataset.accTab, link.dataset.accQuery);
            closeSide();
        });
    });
    var burger = document.getElementById('ac-burger');
    if (burger && side) {
        burger.addEventListener('click', function () { side.classList.toggle('open'); });
        document.addEventListener('click', function (e) {
            if (side.classList.contains('open') && !side.contains(e.target) && !burger.contains(e.target)) closeSide();
        });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeSide(); });
    }

    // Light / dark (shared key with the other dashboards).
    var theme = document.getElementById('ac-theme');
    function paintTheme() {
        var icon = theme && theme.querySelector('i');
        if (icon) icon.className = 'fas ' + (document.body.classList.contains('dark') ? 'fa-sun' : 'fa-moon');
    }
    if (theme) {
        theme.addEventListener('click', function () {
            document.body.classList.toggle('dark');
            try { localStorage.setItem('darkMode', document.body.classList.contains('dark')); } catch (err) {}
            paintTheme();
        });
        paintTheme();
    }

    // Approve / reject an online payment (policy-protected POST endpoints), then refresh the page.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-review-url]');
        if (!btn) return;
        btn.disabled = true;
        fetch(btn.dataset.reviewUrl, { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value } })
            .then(function (r) {
                if (!r.ok) throw new Error(r.status);
                say('انجام شد.');
                reload();
            })
            .catch(function () {
                btn.disabled = false;
                say('انجام عملیات ممکن نبود. دسترسی یا اتصال را بررسی کنید.', true);
            });
    });

    // Command palette (Ctrl/Cmd + K): jump to a page or start an operation.
    var pal = document.getElementById('ac-pal');
    var palInput = document.getElementById('ac-pal-q');
    var palList = document.getElementById('ac-pal-list');
    var items = [], shown = [], sel = 0;
    function buildItems() {
        var v = view() || { dataset: {} };
        items = [];
        document.querySelectorAll('#ac-side [data-acc-tab]').forEach(function (a) {
            var icon = a.querySelector('i');
            items.push({ label: a.textContent.trim(), hint: 'رفتن به', icon: icon ? icon.className.replace(' ic', '') : 'fas fa-arrow-left',
                         run: function () { openTab(a.dataset.accTab, a.dataset.accQuery); } });
        });
        [['سند جدید', 'newVoucher', 'fa-plus'], ['صدور فیش نقدی', 'newBill', 'fa-receipt'], ['ثبت بودجه', 'newBudget', 'fa-chart-pie'],
         ['طرف حساب جدید', 'newParty', 'fa-user-plus'], ['حساب جدید', 'newAccount', 'fa-sitemap']].forEach(function (x) {
            if (v.dataset[x[1]]) items.push({ label: x[0], hint: 'عملیات', icon: 'fas ' + x[2], run: function () { openModal(v.dataset[x[1]]); } });
        });
    }
    function paintPal() {
        var q = palInput.value.trim();
        shown = items.filter(function (it) { return !q || it.label.indexOf(q) !== -1; });
        sel = Math.min(sel, Math.max(shown.length - 1, 0));
        palList.innerHTML = '';
        if (!shown.length) { palList.innerHTML = '<div class="ac-pal-empty">موردی پیدا نشد.</div>'; return; }
        shown.forEach(function (it, i) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'ac-pal-item' + (i === sel ? ' sel' : '');
            b.setAttribute('role', 'option');
            b.innerHTML = '<span class="pic"><i class="' + it.icon + '" aria-hidden="true"></i></span><span></span><span class="hint"></span>';
            b.children[1].textContent = it.label;
            b.children[2].textContent = it.hint;
            b.addEventListener('click', function () { pick(it); });
            palList.appendChild(b);
        });
    }
    function pick(it) { pal.close(); it.run(); }
    function openPal() {
        buildItems();
        palInput.value = '';
        sel = 0;
        paintPal();
        if (!pal.open) pal.showModal();
        palInput.focus();
    }
    if (pal && palInput) {
        var openBtn = document.getElementById('ac-pal-open');
        if (openBtn) openBtn.addEventListener('click', openPal);
        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pal.open ? pal.close() : openPal(); }
        });
        palInput.addEventListener('input', function () { sel = 0; paintPal(); });
        palInput.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); paintPal(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paintPal(); }
            else if (e.key === 'Enter' && shown[sel]) { e.preventDefault(); pick(shown[sel]); }
        });
        pal.addEventListener('click', function (e) { if (e.target === pal) pal.close(); });
    }
})();
