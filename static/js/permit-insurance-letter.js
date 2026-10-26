/* Permit file, step 6: the dehyari's letter introducing the owner to the Social Security Organisation, drawn on the blank
   dehyari letterhead from the file's data (json_script #pfi-data) and the form on the page, downloaded as PDF or printed. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfi-data').textContent), L = data.letter;
  var canvas = document.getElementById('pfi-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', FONT = 'Vazirmatn, Tahoma, sans-serif', letterhead = null;
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }).replace(/\./g, '٫'); }
  function slashed(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '/'); }

  function put(text, x, y, size, color, align) {
    text = fa(text); if (!text) return;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = align || 'right'; ctx.fillStyle = color || INK; ctx.font = size + 'px ' + FONT;
    ctx.fillText(text, x, y); ctx.restore();
  }
  function paragraph(parts, x1, x0, y, lineH, size) {
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 14), ink: false, dots: true }); }
    });
    var space = size * 0.32, x = x1, line = y;
    words.forEach(function (w) {
      ctx.font = (w.ink ? '' : 'bold ') + size + 'px ' + FONT;
      var width = ctx.measureText(w.text).width;
      if (x - width < x0) { x = x1; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? '#6b7280' : BLACK);
      ctx.fillText(w.text, x, line);
      x -= width + space;
    });
    return line;
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.drawImage(letterhead, 0, 0, W, H);
    put(L.number, 300, 143, 30); put(L.date, 300, 190, 30);
    ctx.save(); ctx.fillStyle = BLACK; ctx.font = 'bold 36px ' + FONT; ctx.direction = 'rtl'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(fa('ریاست محترم سازمان تامین اجتماعی - شعبه ' + (L.branch || '…………')), 1245, 520); ctx.restore();
    paragraph([{ t: 'با سلام و احترام؛' }], 1245, 160, 610, 60, 32);
    var last = paragraph([
      { t: 'نظر به اینکه آقای' }, { v: L.owner, w: 20 }, { t: 'فرزند' }, { v: L.father, w: 14 }, { t: 'مبلغ' }, { v: L.base ? slashed(L.base) : '', w: 14 },
      { t: 'ریال بابت عوارض صدور پروانه ساختمان جهت' }, { v: L.area, w: 8 }, { t: 'متر مربع زیر بنا در معبر' }, { v: L.street, w: 6 },
      { t: 'متری به دهیاری' }, { v: L.village, w: 12 }, { t: 'پرداخت کرده، خواهشمند است دستور فرمایید نسبت به دریافت حق بیمه اقدام گردد.' }
    ], 1245, 160, 700, 68, 33);
    if (L.no_formula) paragraph([{ t: '(این دهیاری فاقد فرمول محاسبه عوارض می‌باشد.)' }], 1245, 160, last + 110, 60, 28);
    ctx.save(); ctx.fillStyle = BLACK; ctx.font = 'bold 34px ' + FONT; ctx.direction = 'rtl'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('با تشکر', 440, 1100); ctx.fillText(fa('دهیاری ' + (L.village || '')), 440, 1155); ctx.fillText('مهر و امضای دهیار', 440, 1210); ctx.restore();
  }

  function read() {
    var form = document.getElementById('pfi-form');
    if (!form) return;
    var f = form.elements;
    L.number = f.number.value; L.date = f.date.value; L.branch = f.branch.value; L.base = String(f.base.value).replace(/\D/g, '');
    L.area = f.area.value; L.street = f.street.value; L.no_formula = f.no_formula.checked;
  }
  var form = document.getElementById('pfi-form');
  if (form) { var again = function () { read(); draw(); }; form.addEventListener('input', again); form.addEventListener('change', again); }

  document.getElementById('pfi-dl').addEventListener('click', async function () {
    var jpg = await PdfLite.toJpeg(canvas); PdfLite.save(PdfLite.make([jpg], W, H), 'social-security-letter-' + data.file + '.pdf');
  });
  document.getElementById('pfi-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'), im = doc.createElement('img');
    doc.title = 'نامه‌ی معرفی به تامین اجتماعی';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}';
    doc.head.appendChild(style); im.src = canvas.toDataURL('image/jpeg', 0.92); doc.body.appendChild(im);
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  var img = new Image();
  img.onload = function () {
    letterhead = img;
    document.fonts.load('30px Vazirmatn').then(function () { return document.fonts.load('bold 30px Vazirmatn'); }).then(function () {
      document.getElementById('pfi-loading').hidden = true; read(); draw();
    });
  };
  img.src = data.blank.letter;
})();
