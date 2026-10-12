/* Voucher form: add/remove lines and show live totals + balance badge. The server re-checks everything. */
(function () {
    var form = document.getElementById('voucher-form');
    if (!form) return;
    var body = form.querySelector('#lines tbody');
    var template = document.getElementById('line-template');
    var fa = '۰۱۲۳۴۵۶۷۸۹';
    function toNumber(text) {
        var latin = String(text || '').replace(/[۰-۹]/g, function (d) { return fa.indexOf(d); })
            .replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 1632; }).replace(/[^0-9]/g, '');
        return latin ? parseInt(latin, 10) : 0;
    }
    function show(n) {
        return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '٬').replace(/\d/g, function (d) { return fa[d]; });
    }
    function recalc() {
        var debit = 0, credit = 0;
        body.querySelectorAll('tr.line').forEach(function (row) {
            debit += toNumber(row.querySelector('[name=debit]').value);
            credit += toNumber(row.querySelector('[name=credit]').value);
        });
        form.querySelector('#sum-debit').textContent = show(debit);
        form.querySelector('#sum-credit').textContent = show(credit);
        var badge = form.querySelector('#balance-badge'), ok = debit === credit && debit > 0;
        badge.textContent = ok ? 'تراز' : 'بی‌حساب';
        badge.className = 'badge ' + (ok ? 'bg-success' : 'bg-danger');
    }
    form.querySelector('#add-line').addEventListener('click', function () {
        body.appendChild(template.content.cloneNode(true));
        recalc();
    });
    form.addEventListener('click', function (e) {
        var btn = e.target.closest('.remove-line');
        if (!btn) return;
        if (body.querySelectorAll('tr.line').length > 1) btn.closest('tr').remove();
        recalc();
    });
    form.addEventListener('input', function (e) { if (e.target.classList.contains('amount')) recalc(); });
    recalc();
})();
