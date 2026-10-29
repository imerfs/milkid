/* Construction without a permit, step 1: the defence form (فرم ارائه دفاعیات و توضیحات ذینفع یا نماینده قانونی متخلف ساختمانی) for the
   Article 99 commission, typeset in the browser from the file's data (json_script #pdf-data), downloaded as PDF or printed. The owner
   signs and leaves a fingerprint; the dehyari fills the confirmation box at the bottom by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pdf-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREY = '#6b7280', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var R = 1235, L = 150;
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }

  function text(t, x, y, size, opts) {
    opts = opts || {};
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = opts.align || 'right';
    ctx.fillStyle = opts.color || BLACK; ctx.font = (opts.bold ? 'bold ' : '') + size + 'px ' + FONT;
    ctx.fillText(t, x, y);
  }
  // parts: [{t: fixed} | {v: value, w: dots when empty} | {box: 'tick' | 'empty'}] in reading order (right to left)
  function paragraph(parts, y, lineH, size, right, left) {
    right = right || R; left = left || L;
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else if (p.box) words.push({ box: p.box });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 18), ink: false, dots: true }); }
    });
    var space = size * 0.3, x = right, line = y;
    words.forEach(function (w) {
      if (w.box) {
        var bw = size * 0.9;
        if (x - bw < left) { x = right; line += lineH; }
        ctx.strokeStyle = BLACK; ctx.lineWidth = 3; ctx.strokeRect(x - bw, line - bw / 2, bw, bw);
        if (w.box === 'tick') { ctx.strokeStyle = INK; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(x - bw + 5, line); ctx.lineTo(x - bw / 2, line + bw / 2 - 5); ctx.lineTo(x - 4, line - bw / 2 + 2); ctx.stroke(); }
        x -= bw + space; return;
      }
      ctx.font = (w.ink ? 'bold ' : '') + size + 'px ' + FONT;
      var width = ctx.measureText(w.text).width;
      if (x - width < left) { x = right; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? GREY : BLACK);
      ctx.fillText(w.text, x, line);
      x -= width + space;
    });
    return line;
  }
  function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function draw() {
    var f = data.form;
    ctx.clearRect(0, 0, W, H); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    text('فرم ارائه دفائیات و توضیحات ذینفع یا نماینده قانونی متخلف ساختمانی', W / 2, 95, 38, { bold: true, align: 'center' });
    text('بسمه تعالی', W / 2, 230, 34, { bold: true, align: 'center' });
    text('اعضاء محترم کمیسیون تبصره ۲ بند ۳ ماده ۹۹', R, 320, 40, { bold: true });
    text('سلام علیکم', R, 400, 32);
    var y = paragraph([{ t: 'بااحترام، به استحضار می‌رساند اینجانب آقای/خانم' }, { v: f.name, w: 22 }, { t: 'فرزند' }, { v: f.father, w: 16 },
      { t: 'با شماره تلفن' }, { v: f.phone, w: 16 }, { t: 'ساکن روستای' }, { v: f.village, w: 12 }, { t: 'واقع در بخش' }, { v: f.district, w: 10 },
      { t: 'شهرستان' }, { v: f.county, w: 10 }, { t: 'جمعا به میزان' }, { v: f.area, w: 8 }, { t: 'متر مربع بنای (بدون اخذ پروانه' },
      { box: f.status === 'without' ? 'tick' : 'empty' }, { t: 'مازاد بر پروانه' }, { box: f.status === 'over' ? 'tick' : 'empty' },
      { t: ') غیر مجاز به علل ذیل که شرح خواهم داد احداث نموده‌ام، دفاعیات اینجانب یا نماینده قانونی اینجانب برای استحضار و طرح در کمیسیون ماده ۹۹ تقدیم می‌گردد.' }],
      490, 68, 31, R, 150);
    text('شرح علل تخلف و دفاعیات اینجانب:', R, y + 85, 32, { bold: true });
    text('(تذکر: در صورت نیاز توضیحات بیشتر را پشت برگه و مستندات لازم را ضمیمه فرمائید)', R, y + 130, 25, { color: GREY });
    var e = paragraph([{ v: f.explanation, w: 60 }], y + 205, 60, 30, R, 150);
    var sy = e + 110;
    text('نام و نام خانوادگی ذینفع یا نماینده قانونی: ' + fa(f.name), 820, sy, 30, { bold: true });
    text('امضاء :', 820, sy + 62, 30, { bold: true });
    text('اثر انگشت :', 820, sy + 124, 30, { bold: true });
    text('تاریخ: ' + fa(f.date), 820, sy + 186, 30, { bold: true });
    var bottom = sy + 235;
    ctx.strokeStyle = BLACK; ctx.lineWidth = 4; roundRect(70, 150, W - 140, bottom - 150, 120); ctx.stroke();
    text('محل تاییدیه دهیاری ، بخشداری یا فرمانداری', W / 2, bottom + 60, 34, { bold: true, align: 'center' });
    var top = bottom + 95;
    ctx.lineWidth = 3; roundRect(70, top, W - 140, 215, 36); ctx.stroke();
    paragraph([{ t: 'فرم فوق در حضور اینجانب :' }, { v: f.dehyari, w: 26 }, { t: 'تکمیل و داخل پرونده نامبرده فوق درج گردید.' }], top + 55, 58, 29, R, 160);
    text('سمت : دهیار', R, top + 165, 29, { bold: true }); text('مهر و امضاء :', 700, top + 165, 29, { bold: true }); text('تاریخ :', 330, top + 165, 29, { bold: true });
  }

  function pageCanvas() { var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); return c; }
  var form = document.getElementById('pdf-form');
  function read() {
    form.querySelectorAll('[name]').forEach(function (el) {
      if (el.name in data.form) data.form[el.name] = el.type === 'radio' ? (el.checked ? el.value : data.form[el.name]) : el.value;
    });
    draw();
  }
  form.addEventListener('input', read); form.addEventListener('change', read);
  document.querySelectorAll('[data-suggest]').forEach(function (b) {
    b.addEventListener('click', function () {
      var box = form.querySelector('[name=explanation]'), add = b.getAttribute('data-suggest');
      if (box.value.indexOf(add) === -1) box.value = (box.value ? box.value + ' ' : '') + add;
      read();
    });
  });

  document.getElementById('pdf-dl').addEventListener('click', async function () {
    PdfLite.save(PdfLite.make([await PdfLite.toJpeg(pageCanvas())], W, H), 'defence-form-' + data.file + '.pdf');
  });
  document.getElementById('pdf-print').addEventListener('click', function () {
    var win = window.open('', '_blank'), doc = win.document, style = doc.createElement('style'), im = doc.createElement('img');
    doc.title = 'چاپ فرم دفاعیه';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}';
    doc.head.appendChild(style); im.src = pageCanvas().toDataURL('image/jpeg', 0.92); doc.body.appendChild(im);
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  Promise.all([document.fonts.load('30px Vazirmatn'), document.fonts.load('bold 30px Vazirmatn')]).then(function () {
    document.getElementById('pff-loading').hidden = true; read();
  });
})();
