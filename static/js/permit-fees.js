/* Permit file, step 5: the financial officer's fee list (live total, a suggested amount from a row's factors) and the printable
   fee sheet. Everything the server decides is re-checked there; this only helps the typing. */
(function () {
  'use strict';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function latin(t) { return String(t || '').replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 0x660; }); }
  function number(t) {
    var s = latin(t).replace(/[,٬\s]/g, '').replace(/[\/٫]/g, '.');
    var n = parseFloat(s);
    return isFinite(n) ? n : NaN;
  }
  function fa(n) { return String(n).replace(/\d/g, function (d) { return FA[d]; }); }
  function money(n) { return fa(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '٬')); }

  var form = document.getElementById('pfe-form');
  if (form) {
    var total = document.getElementById('pfe-total');
    var update = function () {
      var sum = 0;
      form.querySelectorAll('tr[data-row]').forEach(function (tr) {
        var on = tr.querySelector('input[type=checkbox]');
        tr.classList.toggle('on', on.checked);
        var n = number(tr.querySelector('[data-amount]').value);
        if (on.checked && isFinite(n)) sum += n;
      });
      form.querySelectorAll('[data-extra]').forEach(function (el) { var n = number(el.value); if (isFinite(n)) sum += n; });
      total.textContent = money(sum);
    };
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.querySelectorAll('[data-suggest]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var tr = btn.closest('tr'), product = 1, used = 0;
        tr.querySelectorAll('[data-fac]').forEach(function (el) { var n = number(el.value); if (isFinite(n)) { product *= n; used++; } });
        if (!used) return;
        tr.querySelector('[data-amount]').value = Math.round(product);
        tr.querySelector('input[type=checkbox]').checked = true;
        update();
      });
    });
    update();
  }

  var print = document.getElementById('pfe-print');
  if (print) {
    print.addEventListener('click', function () {
      var sheet = document.querySelector('.pfe-sheet'), win = window.open('', '_blank');
      if (!sheet || !win) return;
      var doc = win.document, style = doc.createElement('style');
      doc.title = 'فرم محاسبه عوارض و بهای خدمات';
      doc.documentElement.setAttribute('dir', 'rtl'); doc.documentElement.setAttribute('lang', 'fa');
      style.textContent = '@page{size:A4;margin:14mm}body{font-family:Vazirmatn,Tahoma,sans-serif;font-size:13px;color:#111}table{width:100%;border-collapse:collapse}th,td{border:1px solid #444;padding:6px 8px;text-align:right}th{background:#eee}.sign{margin-top:48px;display:flex;justify-content:space-between}button{display:none}';
      doc.head.appendChild(style);
      var copy = doc.importNode(sheet, true);
      copy.querySelectorAll('button').forEach(function (b) { b.remove(); });
      doc.body.appendChild(copy);
      var sign = doc.createElement('div'); sign.className = 'sign';
      ['امضای متقاضی', 'مهر و امضای مسئول مالی', 'مهر و امضای دهیار'].forEach(function (t) { var s = doc.createElement('span'); s.textContent = t; sign.appendChild(s); });
      doc.body.appendChild(sign);
      win.focus(); setTimeout(function () { win.print(); }, 400);
    });
  }
})();
