/* Trade screens of the accountant workspace: line tables (invoices, stock documents, formulas, consignment), the profit
   percent of a purchase line, and the point of sale. Numbers and money arithmetic come from accounting-money.js (AccMoney). */
(function () {
    var M = window.AccMoney;
    var num = M.num, toFa = M.toFa, toLatin = M.toLatin, fmtRial = M.fmtRial, lineTotal = M.lineTotal, lineProfit = M.lineProfit,
        sellFromMargin = M.sellFromMargin, marginFromSell = M.marginFromSell, matchProducts = M.matchProducts;
    function say(message, bad) { if (window.AccPanel) window.AccPanel.say(message, bad); }

    // ---------- trade: line tables (invoices, stock documents, formulas, consignment) ----------
    function recalcTrade(form) {
        var subtotal = 0, profit = 0;
        form.querySelectorAll('[data-trade-lines] tbody tr').forEach(function (row) {
            var q = row.querySelector('[data-trade-qty]'), pr = row.querySelector('[data-trade-unit_price]'), d = row.querySelector('[data-trade-discount]');
            var cell = row.querySelector('[data-trade-rowtotal]');
            if (!cell || !q || !pr) return;
            var total = lineTotal(q.value, pr.value, d && d.value);
            subtotal += total;
            var sp = row.querySelector('[data-trade-sell_price]');
            if (sp && sp.value) profit += lineProfit(q.value, pr.value, sp.value);
            cell.textContent = fmtRial(Math.max(total, 0));
        });
        var box = form.querySelector('[data-trade-subtotal]');
        if (box) box.textContent = fmtRial(subtotal);
        var pbox = form.querySelector('[data-trade-profit]');
        if (pbox) pbox.textContent = (profit < 0 ? '−' : '') + fmtRial(Math.abs(profit));
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
        if (price && !price.value) price.value = fmtRial(Number(form.dataset.price === 'buy' ? option.dataset.buy : option.dataset.price));
        if (cost && !cost.value) cost.value = fmtRial(Number(option.dataset.buy));
        var sell = row.querySelector('[data-trade-sell_price]');
        if (sell && !sell.value && Number(option.dataset.price)) { sell.value = fmtRial(Number(option.dataset.price)); syncMargin(sell); }
        recalcTrade(form);
    });
    // purchase lines: profit % <-> selling price, both directions, from the buying price
    function syncMargin(target) {
        var row = target.closest('tr'), price = row.querySelector('[data-trade-unit_price]'), pct = row.querySelector('[data-trade-margin]'),
            sell = row.querySelector('[data-trade-sell_price]');
        if (!price || !pct || !sell) return;
        var buy = num(price.value);
        if (target === sell) {
            var margin = sell.value ? marginFromSell(buy, sell.value) : null;
            pct.value = margin === null ? '' : toFa(String(margin));
        } else if (buy > 0 && pct.value !== '') {
            sell.value = fmtRial(sellFromMargin(buy, pct.value));
        }
    }
    document.addEventListener('input', function (e) {
        var form = e.target.closest && e.target.closest('[data-trade-form]');
        if (!form) return;
        if (e.target.matches('[data-trade-unit_price],[data-trade-margin],[data-trade-sell_price]')) syncMargin(e.target);
        recalcTrade(form);
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
            var line = lineTotal(qty, price, 0);
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
            var stock = document.createElement('td'); stock.className = 'num-cell'; stock.textContent = toFa(String(product.stock)) + ' ' + product.unit + (product.expiry ? ' · انقضا ' + toFa(product.expiry) : '');
            var qtyCell = document.createElement('td'), qtyInput = document.createElement('input');
            qtyInput.className = 'ac-in'; qtyInput.setAttribute('data-pos-qty', ''); qtyInput.value = '1'; qtyInput.dir = 'ltr'; qtyInput.style.width = '5rem';
            qtyInput.setAttribute('aria-label', 'تعداد'); qtyCell.appendChild(qtyInput);
            var priceCell = document.createElement('td'), priceInput = document.createElement('input');
            priceInput.className = 'ac-in'; priceInput.setAttribute('data-pos-price', ''); priceInput.setAttribute('data-money', ''); priceInput.value = fmtRial(product.price); priceInput.dir = 'ltr';
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
    function posMatches(root, q) {
        var all = root.querySelector('[data-pos-all]');
        return matchProducts(posState(root).products, q, all && all.checked);
    }
    function posGrid(root) {
        var box = root.querySelector('[data-pos-search]'), grid = root.querySelector('[data-pos-grid]');
        var found = posMatches(root, box ? box.value : ''), shown = found.slice(0, 60);
        grid.innerHTML = '';
        shown.forEach(function (p) {
            var b = document.createElement('button');
            b.type = 'button'; b.className = 'ac-pos-item' + (p.stock > 0 ? '' : ' out'); b.dataset.posPick = p.id;
            var name = document.createElement('b'); name.textContent = p.name;
            var info = document.createElement('span'); info.textContent = 'موجودی ' + toFa(String(p.stock)) + ' ' + p.unit;
            var price = document.createElement('span'); price.textContent = fmtRial(p.price) + ' ریال';
            b.appendChild(name); b.appendChild(info); b.appendChild(price);
            if (p.expiry) { var ex = document.createElement('em'); ex.textContent = 'انقضا ' + toFa(p.expiry); if (p.expiryState) ex.className = p.expiryState; b.appendChild(ex); }
            grid.appendChild(b);
        });
        var more = root.querySelector('[data-pos-count]');
        if (more) more.textContent = found.length > shown.length ? 'نمایش ' + toFa(String(shown.length)) + ' از ' + toFa(String(found.length)) + ' کالا؛ عبارت را دقیق‌تر کنید.'
            : (found.length ? toFa(String(found.length)) + ' کالا' : 'کالایی پیدا نشد.');
    }
    document.addEventListener('input', function (e) {
        var box = e.target.closest && e.target.closest('[data-pos-search]');
        if (box) posGrid(box.closest('[data-pos]'));
    });
    document.addEventListener('change', function (e) {
        if (e.target.matches && e.target.matches('[data-pos-all]')) posGrid(e.target.closest('[data-pos]'));
    });
    document.addEventListener('click', function (e) {
        var pick = e.target.closest && e.target.closest('[data-pos-pick]');
        if (!pick) return;
        var root = pick.closest('[data-pos]'), product = posState(root).products.filter(function (p) { return String(p.id) === pick.dataset.posPick; })[0];
        if (product) posAdd(root, product);
    });
    function posInit() {
        document.querySelectorAll('[data-pos]').forEach(function (root) { if (!root._gridDone) { root._gridDone = true; posGrid(root); } });
    }
    document.addEventListener('htmx:afterSettle', posInit);
    posInit();
    document.addEventListener('keydown', function (e) {
        var box = e.target.closest && e.target.closest('[data-pos-search]');
        if (!box || e.key !== 'Enter') return;
        e.preventDefault();
        var root = box.closest('[data-pos]'), q = box.value.trim();
        if (!q) return;
        var products = posState(root).products;
        var found = products.filter(function (p) { return p.barcode === q || p.code === q; })[0]
            || posMatches(root, q)[0];
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
})();
