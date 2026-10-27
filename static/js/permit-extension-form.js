/* Permit renewal: the owner's request form and the renewal form (نوبت اول / دوم) drawn in the browser from the file's data
   (json_script #pfx-data) and the inputs on the page, downloaded as PDF or printed. Signatures, the owner's fingerprint and the
   stamps are put on the printed paper by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfx-data').textContent), Q = data.req, E = data.form;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, XR = 1290, XL = 110, INK = '#0a1f6e', BLACK = '#111827', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var page = 1, FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }

  function txt(s, x, y, size, color, align, bold) {
    s = fa(s); if (!s) return 0;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = align || 'right'; ctx.fillStyle = color || BLACK;
    ctx.font = (bold ? 'bold ' : '') + size + 'px ' + FONT; var w = ctx.measureText(s).width; ctx.fillText(s, x, y); ctx.restore(); return w;
  }
  function dots(x0, x1, y) { ctx.save(); ctx.strokeStyle = '#9ca3af'; ctx.setLineDash([2, 5]); ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); ctx.restore(); }
  function frame() {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 8; ctx.strokeRect(60, 60, W - 120, H - 120);
    ctx.lineWidth = 2.5; ctx.strokeRect(80, 80, W - 160, H - 160); ctx.restore();
  }
  function paragraph(parts, x1, x0, y, lineH, size) {
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 14), dots: true }); }
    });
    var space = size * 0.32, x = x1, line = y;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    words.forEach(function (w) {
      ctx.font = (w.ink ? '' : 'bold ') + size + 'px ' + FONT;
      var wd = ctx.measureText(w.text).width;
      if (x - wd < x0) { x = x1; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? '#6b7280' : BLACK); ctx.fillText(w.text, x, line); x -= wd + space;
    });
    ctx.restore(); return line;
  }
  function field(label, v, xr, y, w) {
    var lw = txt(label, xr, y, 27, BLACK, 'right', true) + 12; dots(xr - w, xr - lw - 4, y + 14);
    if (v) txt(v, xr - lw - 8, y - 2, 27, INK, 'right');
  }

  function drawRequest() {
    frame();
    txt('بسمه تعالی', 1000, 190, 34, BLACK, 'center', true);
    txt('"فرم درخواست"', XR - 20, 330, 60, BLACK, 'right', true); txt('تاریخ:', 520, 335, 34, BLACK, 'right', true); txt(Q.request_date, 440, 335, 34, INK, 'right');
    txt('شماره: ' + fa(Q.request_no || ''), 360, 410, 28, INK, 'right');
    txt('دهیار روستای ' + (E.village || ''), XR - 20, 480, 44, BLACK, 'right', true);
    txt('با سلام', XR - 20, 570, 34, BLACK, 'right', true);
    var y = paragraph([{ t: 'اینجانب' }, { v: Q.name, w: 18 }, { t: 'فرزند' }, { v: Q.father, w: 12 }, { t: 'با شماره شناسنامه' }, { v: Q.id_number, w: 14 },
      { t: 'ساکن روستای' }, { v: E.village, w: 12 }, { t: '،' }, { v: Q.address, w: 24 },
      { t: 'تقاضای تمدید پروانه را دارم. خواهشمند است در صورت امکان مساعدت فرمایید.' }], XR - 20, XL + 20, 660, 80, 36);
    txt('امضاء و اثرانگشت متقاضی', XR - 40, 1280, 36, BLACK, 'right', true);
    ctx.save(); ctx.strokeStyle = '#9ca3af'; ctx.setLineDash([6, 6]); ctx.lineWidth = 2; ctx.strokeRect(XR - 520, 1130, 480, 100); ctx.restore();
    txt('تلفن تماس:', XR - 20, 1600, 34, BLACK, 'right', true); dots(XR - 520, XR - 220, 1614); txt(Q.phone, XR - 235, 1598, 34, INK, 'right');
    void y;
  }

  function drawRenewal() {
    frame();
    var title = 'تمدید مهلت پروانه (' + (data.term === 2 ? 'نوبت دوم' : 'نوبت اول') + ')';
    txt(title, W / 2, 190, 56, BLACK, 'center', true);
    field('شماره:', E.number, XR - 20, 290, 520); field('تاریخ:', E.date, XR - 20, 350, 520);
    field('روستای:', E.village, 500, 290, 340); field('بخش:', E.section, 500, 350, 340);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(XL, 420, XR - XL, 250, 22); ctx.stroke(); ctx.restore();
    field('کد:', E.code, XR - 40, 470, 400); field('عوارض زیربنا طبق فیش شماره:', E.fee_slip_no, 830, 470, 640);
    field('تاریخ اتمام عملیات ساختمانی:', E.finish_date, XR - 40, 560, 640); field('بیمه کارگران طبق فیش شماره:', E.ins_slip_no, 600, 560, 520);
    paragraph([{ t: 'بر اساس تقاضای شماره' }, { v: Q.request_no, w: 12 }, { t: 'مورخ' }, { v: Q.request_date, w: 12 }, { t: 'آقای / خانم' }, { v: E.owner, w: 18 },
      { t: 'پروانه صادره برای ملک پلاک ثبتی' }, { v: E.registry_plot, w: 14 }, { t: 'واقع در بخش' }, { v: E.section, w: 12 },
      { t: 'از تاریخ' }, { v: E.from_date, w: 12 }, { t: 'برای مدت' }, { v: E.period, w: 10 }, { t: 'تمدید می‌گردد.' }], XR - 20, XL + 20, 780, 78, 33);
    txt('نام و امضاء مسئول فنی دهیاری', 1010, 1100, 30, BLACK, 'center', true); txt(E.tech_name, 1010, 1060, 30, INK, 'center');
    txt('نام و امضاء دهیار', 380, 1100, 30, BLACK, 'center', true); txt(E.dehyari_name, 380, 1060, 30, INK, 'center');
  }

  var DRAW = { 1: drawRequest, 2: drawRenewal };
  function draw(n) { page = n || page; ctx.clearRect(0, 0, W, H); DRAW[page](); }
  function pageCanvas(n) { var keep = page; draw(n); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }
  var form = document.getElementById('pfx-form');
  function read() { form.querySelectorAll('input[name^="q_"]').forEach(function (el) { Q[el.name.slice(2)] = el.value; }); form.querySelectorAll('input[name^="e_"]').forEach(function (el) { E[el.name.slice(2)] = el.value; }); }
  function refresh() { read(); draw(); }
  form.addEventListener('input', refresh);
  document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.addEventListener('click', function () {
    document.querySelectorAll('.pff-tabs button').forEach(function (x) { x.classList.toggle('is-on', x === b); }); draw(parseInt(b.getAttribute('data-page'), 10)); }); });
  document.getElementById('pfx-dl-all').addEventListener('click', async function () {
    var jpgs = []; for (var i = 1; i <= 2; i++) jpgs.push(await PdfLite.toJpeg(pageCanvas(i)));
    PdfLite.save(PdfLite.make(jpgs, W, H), 'permit-renewal-' + data.file + '.pdf');
  });
  document.getElementById('pfx-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'); doc.title = 'چاپ تمدید پروانه';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}'; doc.head.appendChild(style);
    [1, 2].forEach(function (n) { var im = doc.createElement('img'); im.src = pageCanvas(n).toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });
  document.fonts.load('30px Vazirmatn').then(function () { return document.fonts.load('bold 30px Vazirmatn'); }).then(function () {
    document.getElementById('pff-loading').hidden = true; refresh();
  });
})();
