/* Messenger: thread list, thread pane, new-message dialog and polling. Everything the server renders is an HTML fragment. */
(function () {
    var root = document.getElementById('mg');
    if (!root) return;
    var base = root.dataset.base;
    var csrf = (root.querySelector('input[name=csrfmiddlewaretoken]') || {}).value || '';
    var list = document.getElementById('mg-list');
    var pane = document.getElementById('mg-pane');
    var state = { kind: 'all', unread: false, q: '', open: '', sig: root.dataset.sig || '' };
    var welcome = pane.innerHTML;

    function url(path, params) {
        var qs = params ? '?' + new URLSearchParams(params).toString() : '';
        return base + path + qs;
    }
    function get(path, params) { return fetch(url(path, params), { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } }); }
    function post(path, body) {
        body.append('csrfmiddlewaretoken', csrf);
        return fetch(url(path), { method: 'POST', body: body, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'fetch' } });
    }
    function failure(res) {
        return res.json().then(function (j) { return j.error || 'خطا در ارتباط با سرور.'; }, function () { return 'خطا در ارتباط با سرور.'; });
    }

    // ---------- list ----------
    function loadList() {
        var params = { kind: state.kind, q: state.q, open: state.open };
        if (state.unread) params.unread = '1';
        return get('list/', params).then(function (r) { return r.text(); }).then(function (html) { list.innerHTML = html; });
    }
    var typing;
    document.getElementById('mg-q').addEventListener('input', function (e) {
        clearTimeout(typing);
        typing = setTimeout(function () { state.q = e.target.value; loadList(); }, 250);
    });
    root.querySelector('.mg-chips').addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) return;
        if (b.dataset.unread) { state.unread = !state.unread; b.classList.toggle('is-on', state.unread); }
        else {
            state.kind = b.dataset.kind;
            root.querySelectorAll('.mg-chips button[data-kind]').forEach(function (x) { x.classList.toggle('is-on', x === b); });
        }
        loadList();
    });
    list.addEventListener('click', function (e) {
        var row = e.target.closest('.mg-row');
        if (row) openThread(row.dataset.key);
    });

    // ---------- thread ----------
    function toBottom() { var f = document.getElementById('mg-feed'); if (f) f.scrollTop = f.scrollHeight; }
    function bindCompose() {
        var form = document.getElementById('mg-compose');
        if (!form) return;
        var box = form.querySelector('textarea');
        box.addEventListener('input', function () { box.style.height = 'auto'; box.style.height = Math.min(box.scrollHeight, 140) + 'px'; });
        box.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey && form.dataset.kind === 'chat') { e.preventDefault(); form.requestSubmit(); }
        });
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!box.value.trim()) return;
            var data = new FormData(form);
            box.disabled = true;
            post('thread/' + form.dataset.key + '/send/', data).then(function (res) {
                if (!res.ok) return failure(res).then(function (m) { window.alert(m); });
                return res.text().then(function (html) { pane.innerHTML = html; bindCompose(); toBottom(); loadList(); });
            }).finally(function () { box.disabled = false; var b = document.querySelector('#mg-compose textarea'); if (b) b.focus(); });
        });
    }
    function openThread(key) {
        state.open = key;
        root.dataset.view = 'thread';
        return get('thread/' + key + '/').then(function (res) {
            if (!res.ok) { return failure(res).then(function (m) { var note = document.createElement('p'); note.className = 'mg-none'; note.textContent = m; pane.replaceChildren(note); }); }
            return res.text().then(function (html) {
                pane.innerHTML = html;
                bindCompose();
                toBottom();
                list.querySelectorAll('.mg-row').forEach(function (r) { r.classList.toggle('is-on', r.dataset.key === key); });
                var badge = list.querySelector('.mg-row[data-key="' + key + '"] .mg-badge');
                if (badge) badge.remove();
                notifyParent();
            });
        });
    }
    function refreshThread() {
        if (!state.open) return;
        get('thread/' + state.open + '/').then(function (res) { return res.ok ? res.text() : null; }).then(function (html) {
            if (!html) return;
            var tmp = document.createElement('div');
            tmp.innerHTML = html;
            var fresh = tmp.querySelector('#mg-feed'), current = document.getElementById('mg-feed');
            if (fresh && current && fresh.dataset.last !== current.dataset.last) {
                var nearEnd = current.scrollHeight - current.scrollTop - current.clientHeight < 80;
                current.innerHTML = fresh.innerHTML;
                current.dataset.last = fresh.dataset.last;
                if (nearEnd) toBottom();
            }
        });
    }
    pane.addEventListener('click', function (e) {
        if (e.target.closest('[data-act=back]')) { root.dataset.view = 'list'; state.open = ''; pane.innerHTML = welcome; loadList(); }
    });
    pane.addEventListener('change', function (e) {
        if (e.target.id === 'mg-files') { var form = document.getElementById('mg-compose'); form.classList.toggle('has-files', e.target.files.length > 0); }
    });

    // ---------- polling ----------
    function notifyParent() {
        if (window.parent !== window) {
            var total = 0;
            list.querySelectorAll('.mg-badge').forEach(function (b) { total += parseInt(b.textContent.replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); }), 10) || 0; });
            window.parent.postMessage({ messengerUnread: total }, window.location.origin);
        }
    }
    function poll() {
        if (document.hidden) return;
        get('poll/').then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
            if (!j) return;
            if (j.sig !== state.sig) { state.sig = j.sig; loadList().then(notifyParent); refreshThread(); }
            if (window.parent !== window) window.parent.postMessage({ messengerUnread: j.unread }, window.location.origin);
        });
    }
    setInterval(poll, 8000);
    document.addEventListener('visibilitychange', poll);

    // ---------- new message dialog ----------
    var dialog = document.getElementById('mg-new');
    var form = document.getElementById('mg-new-form');
    var dirList = document.getElementById('mg-dir-list');
    var chosen = document.getElementById('mg-chosen');
    var err = document.getElementById('mg-err');
    var nk = { kind: 'chat', org: '', people: [] };
    var token = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

    function renderChosen() {
        chosen.innerHTML = '';
        if (!nk.people.length) { chosen.innerHTML = '<span class="mg-hint">گیرنده را از فهرست انتخاب کنید.</span>'; return; }
        nk.people.forEach(function (p) {
            var chip = document.createElement('span');
            chip.className = 'mg-chip';
            chip.textContent = p.name;
            var x = document.createElement('button');
            x.type = 'button';
            x.setAttribute('aria-label', 'حذف ' + p.name);
            x.innerHTML = '<svg class="mg-i"><use href="#mg-close"/></svg>';
            x.addEventListener('click', function () { nk.people = nk.people.filter(function (q) { return q.id !== p.id; }); renderChosen(); markDirectory(); });
            chip.appendChild(x);
            chosen.appendChild(chip);
        });
    }
    function markDirectory() {
        dirList.querySelectorAll('[data-person]').forEach(function (b) {
            b.classList.toggle('is-on', nk.people.some(function (p) { return p.id === b.dataset.person; }));
        });
    }
    function loadDirectory() {
        var params = { q: document.getElementById('mg-dq').value };
        if (nk.org) params.org = nk.org;
        return get('directory/', params).then(function (r) { return r.text(); }).then(function (html) { dirList.innerHTML = html; markDirectory(); });
    }
    function setKind(kind) {
        nk.kind = kind;
        form.querySelectorAll('.mg-seg button').forEach(function (b) { b.classList.toggle('is-on', b.dataset.kind === kind); });
        form.querySelector('.mg-letter-only').hidden = kind !== 'letter';
        document.getElementById('mg-subject').required = kind === 'letter';
        if (kind === 'chat' && nk.people.length > 1) { nk.people = nk.people.slice(0, 1); renderChosen(); markDirectory(); }
    }
    function openNew(kind) {
        nk.people = []; nk.org = ''; err.hidden = true; form.reset(); renderChosen(); setKind(kind || 'chat');
        document.getElementById('mg-dq').value = '';
        dialog.hidden = false;
        loadDirectory();
        document.getElementById('mg-dq').focus();
    }
    document.getElementById('mg-open-new').addEventListener('click', function () { openNew('chat'); });
    dialog.addEventListener('click', function (e) {
        if (e.target === dialog || e.target.closest('[data-act=close-new]')) dialog.hidden = true;
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !dialog.hidden) dialog.hidden = true; });
    form.querySelector('.mg-seg').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) setKind(b.dataset.kind); });
    document.getElementById('mg-dq').addEventListener('input', function () { clearTimeout(typing); typing = setTimeout(loadDirectory, 250); });
    dirList.addEventListener('click', function (e) {
        var back = e.target.closest('[data-act=orgs]');
        if (back) { nk.org = ''; loadDirectory(); return; }
        var o = e.target.closest('[data-org]');
        if (o) { nk.org = o.dataset.org; document.getElementById('mg-dq').value = ''; loadDirectory(); return; }
        var p = e.target.closest('[data-person]');
        if (!p) return;
        var at = nk.people.findIndex(function (x) { return x.id === p.dataset.person; });
        if (at >= 0) nk.people.splice(at, 1);
        else if (nk.kind === 'chat') nk.people = [{ id: p.dataset.person, name: p.dataset.name }];
        else nk.people.push({ id: p.dataset.person, name: p.dataset.name });
        renderChosen(); markDirectory();
    });
    document.getElementById('mg-new-files').addEventListener('change', function (e) {
        document.getElementById('mg-files-label').textContent = e.target.files.length ? e.target.files.length + ' پیوست' : 'پیوست';
    });
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!nk.people.length) { err.textContent = 'گیرنده را انتخاب کنید.'; err.hidden = false; return; }
        var data = new FormData(form);
        data.append('kind', nk.kind);
        data.append('token', token);
        nk.people.forEach(function (p) { data.append('to', p.id); });
        var btn = document.getElementById('mg-send-new');
        btn.disabled = true; err.hidden = true;
        post('new/', data).then(function (res) {
            if (!res.ok) return failure(res).then(function (m) { err.textContent = m; err.hidden = false; });
            return res.json().then(function (j) {
                token = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
                dialog.hidden = true;
                return loadList().then(function () { return openThread(j.key); });
            });
        }).finally(function () { btn.disabled = false; });
    });

    // ---------- start ----------
    bindCompose();
    if (root.dataset.open) openThread(root.dataset.open);
    if (root.dataset.new) openNew(root.dataset.new === 'letter' ? 'letter' : 'chat');
    notifyParent();
})();
