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
        var url = panel.dataset.url || '';
        var queried = false;   // a menu entry that shares its page with another one (e.g. drafts) wins when its filter is on
        document.querySelectorAll('#ac-side [data-acc-query]').forEach(function (a) {
            if (a.dataset.accTab === v.dataset.tab && url.indexOf(a.dataset.accQuery) !== -1) queried = true;
        });
        document.querySelectorAll('[data-acc-tab]').forEach(function (a) {
            var on = a.dataset.accTab === v.dataset.tab && (a.dataset.accQuery ? url.indexOf(a.dataset.accQuery) !== -1 : !queried);
            a.classList.toggle('active', on);
            if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
        });
        var hidden = (v.dataset.hiddenTabs || '').split(',');
        document.querySelectorAll('[data-acc-tab]').forEach(function (a) { a.hidden = hidden.indexOf(a.dataset.accTab) !== -1; });
        document.querySelectorAll('#ac-side .ac-grp').forEach(function (g) {
            var links = g.querySelectorAll('[data-acc-tab]');
            g.hidden = Array.prototype.every.call(links, function (a) { return a.hidden; });
            if (g.querySelector('.ac-item.active')) g.open = true;
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
    dialog.addEventListener('close', function () {
        // a detail window that changed something while it stayed open (e.g. a paid instalment) refreshes the page behind it
        var dirty = body.querySelector('[data-acc-dirty]');
        body.innerHTML = '';
        if (dirty) reload();
    });

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
    var items = [], shown = [], sel = 0, remote = [], remoteTimer;
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
        shown = items.filter(function (it) { return !q || it.label.indexOf(q) !== -1; }).concat(remote);
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
    // Records from the server (vouchers, parties, accounts, bills, plans, contracts) join the menu entries.
    function searchRemote(q) {
        clearTimeout(remoteTimer);
        var v = view();
        if (q.length < 2 || !v || !v.dataset.searchUrl) { remote = []; paintPal(); return; }
        remoteTimer = setTimeout(function () {
            fetch(v.dataset.searchUrl + '?q=' + encodeURIComponent(q), { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : { results: [] }; })
                .then(function (data) {
                    if (palInput.value.trim() !== q) return;
                    remote = (data.results || []).map(function (r) {
                        return { label: r.label, hint: r.kind + (r.sub ? ' · ' + r.sub : ''), icon: 'fas fa-magnifying-glass',
                                 run: function () { if (r.action === 'modal') openModal(r.url); else openTab(r.tab, r.query); } };
                    });
                    paintPal();
                });
        }, 250);
    }
    function openPal() {
        buildItems();
        palInput.value = '';
        remote = [];
        sel = 0;
        paintPal();
        if (!pal.open) pal.showModal();
        palInput.focus();
    }
    if (pal && palInput) {
        palInput.placeholder = 'صفحه، سند، طرف حساب، حساب، فیش، تقسیط یا قرارداد را جستجو کنید...';
        var openBtn = document.getElementById('ac-pal-open');
        if (openBtn) openBtn.addEventListener('click', openPal);
        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pal.open ? pal.close() : openPal(); }
        });
        palInput.addEventListener('input', function () { sel = 0; paintPal(); searchRemote(palInput.value.trim()); });
        palInput.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); paintPal(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); paintPal(); }
            else if (e.key === 'Enter' && shown[sel]) { e.preventDefault(); pick(shown[sel]); }
        });
        pal.addEventListener('click', function (e) { if (e.target === pal) pal.close(); });
    }

    // ---------- calculator (safe expression parser, no eval) ----------
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function toLatin(text) {
        return String(text).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 1632; })
            .replace(/[٬,،\s]/g, '').replace(/٫/g, '.').replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/٪/g, '%');
    }
    function toFa(text) { return String(text).replace(/\d/g, function (d) { return FA[d]; }); }
    function evaluate(source) {
        var src = toLatin(source), i = 0;
        function peek() { return src[i]; }
        function number() {
            var m = /^\d+(\.\d+)?|^\.\d+/.exec(src.slice(i));
            if (!m) throw new Error('عبارت نامعتبر است.');
            i += m[0].length;
            return parseFloat(m[0]);
        }
        function factor() {
            var value;
            if (peek() === '-') { i++; return -factor(); }
            if (peek() === '+') { i++; return factor(); }
            if (peek() === '(') { i++; value = expr(); if (peek() !== ')') throw new Error('پرانتز بسته نشده است.'); i++; }
            else value = number();
            while (peek() === '%') { i++; value = value / 100; }
            return value;
        }
        function term() {
            var value = factor();
            while (peek() === '*' || peek() === '/') {
                var op = src[i++], right = factor();
                if (op === '/' && right === 0) throw new Error('تقسیم بر صفر ممکن نیست.');
                value = op === '*' ? value * right : value / right;
            }
            return value;
        }
        function expr() {
            var value = term();
            while (peek() === '+' || peek() === '-') { var op = src[i++], right = term(); value = op === '+' ? value + right : value - right; }
            return value;
        }
        if (!src) return null;
        var result = expr();
        if (i < src.length) throw new Error('عبارت نامعتبر است.');
        return result;
    }
    function showCalc(root) {
        var input = root.querySelector('[data-calc-input]'), out = root.querySelector('[data-calc-result]');
        try {
            var value = evaluate(input.value);
            out.className = '';
            out.textContent = value === null ? '' : toFa((Math.round(value * 1e6) / 1e6).toLocaleString('en', { maximumFractionDigits: 6 })).replace(/,/g, '٬');
        } catch (err) { out.className = 'ac-bad-text'; out.textContent = err.message; }
    }
    document.addEventListener('click', function (e) {
        var key = e.target.closest('[data-calc]');
        if (!key) return;
        var root = key.closest('[data-calc-root]'), input = root.querySelector('[data-calc-input]'), k = key.dataset.calc;
        if (k === 'C') input.value = '';
        else if (k === '=') { showCalc(root); return; }
        else input.value += k;
        showCalc(root);
        input.focus();
    });
    document.addEventListener('input', function (e) {
        var input = e.target.closest && e.target.closest('[data-calc-input]');
        if (input) showCalc(input.closest('[data-calc-root]'));
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target.closest && e.target.closest('[data-calc-input]')) { e.preventDefault(); showCalc(e.target.closest('[data-calc-root]')); }
    });

    // ---------- tools tab: words, dates, loan ----------
    function money(n) { return toFa(Number(n).toLocaleString('en')).replace(/,/g, '٬'); }
    document.addEventListener('submit', function (e) {
        var form = e.target.closest('[data-tool]');
        if (!form) return;
        e.preventDefault();
        var out = form.querySelector('[data-tool-out]'), params = new URLSearchParams(new FormData(form));
        out.textContent = '...';
        fetch(form.dataset.url + '?' + params.toString(), { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
            if (d.error) { out.textContent = d.error; return; }
            if (form.dataset.tool === 'words') out.textContent = d.rial;
            else if (form.dataset.tool === 'date') out.textContent = toFa(d.jalali) + ' شمسی = ' + d.gregorian + ' میلادی (' + d.weekday + ')';
            else {
                var rows = d.schedule.map(function (r) { return '<tr><td>' + toFa(r.n) + '</td><td>' + money(r.payment) + '</td><td>' + money(r.interest) + '</td><td>' + money(r.balance) + '</td></tr>'; }).join('');
                out.innerHTML = '<p>قسط ماهانه: <b>' + money(d.payment) + '</b> ریال · جمع پرداخت: ' + money(d.total) + ' · سود کل: ' + money(d.interest) + '</p>' +
                    '<div class="ac-table-wrap"><table><thead><tr><th>قسط</th><th>مبلغ</th><th>سود</th><th>مانده</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
            }
        }).catch(function () { out.textContent = 'اتصال به سرور برقرار نشد.'; });
    }, true);

    // ---------- trade: line tables (invoices, stock documents, formulas, consignment) ----------
    function num(text) { var n = parseFloat(toLatin(text || '')); return isNaN(n) ? 0 : n; }
    function recalcTrade(form) {
        var subtotal = 0;
        form.querySelectorAll('[data-trade-lines] tbody tr').forEach(function (row) {
            var q = row.querySelector('[data-trade-qty]'), pr = row.querySelector('[data-trade-unit_price]'), d = row.querySelector('[data-trade-discount]');
            var cell = row.querySelector('[data-trade-rowtotal]');
            if (!cell || !q || !pr) return;
            var total = Math.round(num(q.value) * num(pr.value)) - num(d && d.value);
            subtotal += total;
            cell.textContent = toFa(Math.max(total, 0).toLocaleString('en')).replace(/,/g, '٬');
        });
        var box = form.querySelector('[data-trade-subtotal]');
        if (box) box.textContent = toFa(subtotal.toLocaleString('en')).replace(/,/g, '٬');
    }
    document.addEventListener('click', function (e) {
        var add = e.target.closest('[data-trade-add]');
        if (add) {
            var form = add.closest('[data-trade-form]'), tpl = form.querySelector('[data-trade-template]');
            form.querySelector('[data-trade-lines] tbody').appendChild(tpl.content.cloneNode(true));
            return;
        }
        var rem = e.target.closest('[data-trade-remove]');
        if (rem) {
            var row = rem.closest('tr'), body = row.parentNode, owner = rem.closest('[data-trade-form]');
            if (body.children.length > 1) row.remove();
            else row.querySelectorAll('input,select').forEach(function (el) { el.value = ''; });
            recalcTrade(owner);
        }
    });
    document.addEventListener('change', function (e) {
        var select = e.target.closest && e.target.closest('[data-trade-product]');
        if (!select) return;
        var form = select.closest('[data-trade-form]'), option = select.options[select.selectedIndex], row = select.closest('tr');
        if (!option || !option.dataset.price) return;
        var price = row.querySelector('[data-trade-unit_price]'), cost = row.querySelector('[data-trade-unit_cost]');
        if (price && !price.value) price.value = form.dataset.price === 'buy' ? option.dataset.buy : option.dataset.price;
        if (cost && !cost.value) cost.value = option.dataset.buy;
        recalcTrade(form);
    });
    document.addEventListener('input', function (e) {
        var form = e.target.closest && e.target.closest('[data-trade-form]');
        if (form) recalcTrade(form);
    });

    // ---------- trade: point of sale ----------
    function posState(root) {
        if (!root._pos) {
            var data = root.querySelector('#pos-products');
            root._pos = { products: data ? JSON.parse(data.textContent) : [], vat: parseFloat(root.dataset.vat) || 0 };
        }
        return root._pos;
    }
    function posRender(root) {
        var rows = root.querySelectorAll('[data-pos-cart] tr[data-id]'), subtotal = 0, hidden = root.querySelector('[data-pos-hidden]');
        hidden.innerHTML = '';
        rows.forEach(function (row) {
            var qty = num(row.querySelector('[data-pos-qty]').value), price = num(row.querySelector('[data-pos-price]').value);
            var line = Math.round(qty * price);
            subtotal += line;
            row.querySelector('[data-pos-line]').textContent = toFa(line.toLocaleString('en')).replace(/,/g, '٬');
            [['product', row.dataset.id], ['qty', String(qty)], ['unit_price', String(price)]].forEach(function (pair) {
                var input = document.createElement('input');
                input.type = 'hidden'; input.name = pair[0]; input.value = pair[1];
                hidden.appendChild(input);
            });
        });
        var tax = Math.round(subtotal * posState(root).vat / 100);
        var fmt = function (n) { return toFa(n.toLocaleString('en')).replace(/,/g, '٬'); };
        root.querySelector('[data-pos-subtotal]').textContent = fmt(subtotal);
        var taxBox = root.querySelector('[data-pos-tax]');
        if (taxBox) taxBox.textContent = fmt(tax);
        root.querySelector('[data-pos-total]').textContent = fmt(subtotal + tax);
        root.querySelector('[data-pos-pay]').disabled = !rows.length;
        var empty = root.querySelector('[data-pos-empty]');
        if (empty) empty.hidden = rows.length > 0;
    }
    function posAdd(root, product) {
        var body = root.querySelector('[data-pos-cart]'), existing = body.querySelector('tr[data-id="' + product.id + '"]');
        if (existing) {
            var qty = existing.querySelector('[data-pos-qty]');
            qty.value = String(num(qty.value) + 1);
        } else {
            var row = document.createElement('tr');
            row.dataset.id = product.id;
            var name = document.createElement('td'); name.textContent = product.name + ' (' + product.code + ')';
            var stock = document.createElement('td'); stock.className = 'num-cell'; stock.textContent = toFa(String(product.stock)) + ' ' + product.unit;
            var qtyCell = document.createElement('td'), qtyInput = document.createElement('input');
            qtyInput.className = 'ac-in'; qtyInput.setAttribute('data-pos-qty', ''); qtyInput.value = '1'; qtyInput.dir = 'ltr'; qtyInput.style.width = '5rem';
            qtyInput.setAttribute('aria-label', 'تعداد'); qtyCell.appendChild(qtyInput);
            var priceCell = document.createElement('td'), priceInput = document.createElement('input');
            priceInput.className = 'ac-in'; priceInput.setAttribute('data-pos-price', ''); priceInput.value = String(product.price); priceInput.dir = 'ltr';
            priceInput.style.width = '8rem'; priceInput.setAttribute('aria-label', 'قیمت واحد'); priceCell.appendChild(priceInput);
            var line = document.createElement('td'); line.className = 'num-cell'; line.setAttribute('data-pos-line', ''); line.textContent = '۰';
            var cell = document.createElement('td'), remove = document.createElement('button');
            remove.type = 'button'; remove.className = 'ac-x'; remove.setAttribute('data-pos-remove', ''); remove.setAttribute('aria-label', 'حذف');
            remove.innerHTML = '<i class="fas fa-xmark" aria-hidden="true"></i>'; cell.appendChild(remove);
            [name, stock, qtyCell, priceCell, line, cell].forEach(function (c) { row.appendChild(c); });
            body.appendChild(row);
        }
        posRender(root);
    }
    document.addEventListener('keydown', function (e) {
        var box = e.target.closest && e.target.closest('[data-pos-search]');
        if (!box || e.key !== 'Enter') return;
        e.preventDefault();
        var root = box.closest('[data-pos]'), q = box.value.trim();
        if (!q) return;
        var products = posState(root).products, lower = q.toLowerCase();
        var found = products.filter(function (p) { return p.barcode === q || p.code === q; })[0]
            || products.filter(function (p) { return p.name.toLowerCase().indexOf(lower) !== -1; })[0];
        if (!found) { say('کالایی با «' + q + '» پیدا نشد.', true); return; }
        posAdd(root, found);
        box.value = '';
    });
    document.addEventListener('input', function (e) {
        var root = e.target.closest && e.target.closest('[data-pos]');
        if (root && (e.target.matches('[data-pos-qty]') || e.target.matches('[data-pos-price]'))) posRender(root);
    });
    document.addEventListener('click', function (e) {
        var rem = e.target.closest('[data-pos-remove]');
        if (!rem) return;
        var root = rem.closest('[data-pos]');
        rem.closest('tr').remove();
        posRender(root);
    });

    // ---------- printing: the chosen paper size becomes the page size, the workspace chrome is hidden by print CSS ----------
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-print]');
        if (!btn) return;
        var holder = btn.closest('.ac-printer'), select = holder && holder.querySelector('[data-print-paper]');
        var size = select ? select.value : 'A4';
        if (['A4', 'A5', '80mm auto'].indexOf(size) === -1) size = 'A4';
        var style = document.getElementById('ac-page-style');
        if (!style) { style = document.createElement('style'); style.id = 'ac-page-style'; document.head.appendChild(style); }
        style.textContent = '@page { size: ' + size + '; margin: 8mm; }';
        window.print();
    });

    // ---------- keyboard shortcuts ----------
    var TAB_KEYS = { Digit1: 'overview', Digit2: 'vouchers', Digit3: 'bills', Digit4: 'budget', Digit5: 'trial', Digit6: 'statements',
                     Digit7: 'reports', Digit8: 'builder', Digit9: 'charts' };
    function typing(e) {
        var t = e.target;
        return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
    }
    document.addEventListener('keydown', function (e) {
        var v = view();
        if (!v || dialog.open || (pal && pal.open)) return;
        var hit = null;
        if (e.altKey && !e.ctrlKey && !e.metaKey) {
            if (TAB_KEYS[e.code]) hit = function () { openTab(TAB_KEYS[e.code]); };
            else if (e.code === 'KeyN') hit = function () { openModal(v.dataset.newVoucher); };
            else if (e.code === 'KeyM') hit = function () { openModal(v.dataset.newBill); };
            else if (e.code === 'KeyC') hit = function () { openModal(v.dataset.calcUrl); };
            else if (e.code === 'KeyT') hit = function () { openTab('tools'); };
            else if (e.code === 'KeyH') hit = function () { openModal(v.dataset.helpUrl); };
        } else if (!e.altKey && !e.ctrlKey && !e.metaKey && !typing(e)) {
            if (e.key === 'F2') hit = function () { openModal(v.dataset.newVoucher); };
            else if (e.key === 'F3') hit = function () { openModal(v.dataset.newBill); };
            else if (e.key === 'F4') hit = function () { openTab('vouchers'); };
            else if (e.key === 'F1') hit = function () { openModal(v.dataset.helpUrl); };
        }
        if (hit) { e.preventDefault(); hit(); }
    });
})();
