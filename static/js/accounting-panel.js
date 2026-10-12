/* Accounting workspace on the accountant dashboard: modal dialog, toasts and panel refresh around HTMX. */
(function () {
    var dialog = document.getElementById('acc-modal');
    var body = document.getElementById('acc-modal-body');
    var panel = document.getElementById('acc-panel');
    var toast = document.getElementById('acc-toast');
    if (!dialog || !body || !panel) return;
    var timer;

    function say(message, bad) {
        toast.textContent = message;
        toast.className = 'fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-5 py-3 rounded-lg shadow-lg text-sm text-white '
            + (bad ? 'bg-error-600' : 'bg-success-600');
        clearTimeout(timer);
        timer = setTimeout(function () { toast.className = 'hidden'; }, 4500);
    }
    function reload() {
        htmx.ajax('GET', panel.dataset.url || panel.getAttribute('hx-get'), { target: '#acc-panel', swap: 'innerHTML' });
    }

    // Remember the panel address (tab, filters, page) so a saved change reloads the same view.
    document.body.addEventListener('htmx:afterSwap', function (e) {
        if (e.detail.target === panel) panel.dataset.url = e.detail.pathInfo.finalRequestPath;
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

    // Sidebar shortcuts open a tab of the workspace (optionally with a filter) instead of leaving the page.
    document.querySelectorAll('[data-acc-tab]').forEach(function (link) {
        link.addEventListener('click', function () {
            var holder = panel.querySelector('[data-year]');
            var year = holder && holder.dataset.year ? 'year=' + holder.dataset.year + '&' : '';
            var extra = link.dataset.accQuery ? '&' + link.dataset.accQuery : '';
            htmx.ajax('GET', panel.dataset.base + '?' + year + 'tab=' + link.dataset.accTab + extra,
                      { target: '#acc-panel', swap: 'innerHTML' });
        });
    });

    // Approve / reject an online payment (policy-protected POST endpoints), then refresh the panel.
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
})();
