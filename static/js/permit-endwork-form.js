/* Permit file, the end of the work: the end-of-work certificate («گواهی پایان ساخت») drawn in the browser from the file's data
   (json_script #pfw-data) and the form on the page, downloaded as PDF or printed. The dehyari and the technical manager sign and
   stamp the printed sheet by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfw-data').textContent), F = data.f;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, XR = 1290, XL = 110, INK = '#0a1f6e', BLACK = '#111827', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }
  function val(k) { return F[k] == null ? '' : F[k]; }
  function txt(s, x, y, size, color, align, bold) {
    s = fa(s); if (!s) return 0;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = align || 'right'; ctx.fillStyle = color || BLACK;
    ctx.font = (bold ? 'bold ' : '') + size + 'px ' + FONT; var w = ctx.measureText(s).width; ctx.fillText(s, x, y); ctx.restore(); return w;
  }
  function dots(x0, x1, y) { ctx.save(); ctx.strokeStyle = '#9ca3af'; ctx.setLineDash([2, 5]); ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); ctx.restore(); }
  function line(x0, y0, x1, y1, w) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = w || 2; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); ctx.restore(); }
  function field(label, key, xr, y, w) {
    var lw = txt(label, xr, y, 27, BLACK, 'right', true) + 12; dots(xr - w, xr - lw - 4, y + 14);
    var v = val(key); if (v !== '') txt(v, xr - lw - 8, y - 2, 27, INK, 'right');
  }
  function paragraph(parts, x1, x0, y, lineH, size) {
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 10), dots: true }); }
    });
    var space = size * 0.32, x = x1, ln = y;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    words.forEach(function (w) {
      ctx.font = (w.ink ? '' : 'bold ') + size + 'px ' + FONT;
      var wd = ctx.measureText(w.text).width;
      if (x - wd < x0) { x = x1; ln += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? '#6b7280' : BLACK); ctx.fillText(w.text, x, ln); x -= wd + space;
    });
    ctx.restore(); return ln;
  }

  function draw() {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 8; ctx.strokeRect(60, 60, W - 120, H - 120); ctx.lineWidth = 2.5; ctx.strokeRect(80, 80, W - 160, H - 160); ctx.restore();
    txt('بسمه تعالی', W / 2, 150, 32, BLACK, 'center', true);
    txt('گواهی پایان ساخت', W / 2, 270, 62, BLACK, 'center', true);
    field('شماره:', 'number', 460, 140, 340); field('تاریخ:', 'date', 460, 195, 340);
    field('روستای:', 'village', XR - 20, 350, 380); field('بخش:', 'section', XR - 430, 350, 330);
    field('خانم/آقای:', 'owner', XR - 20, 425, 1180);
    paragraph([{ t: 'در پاسخ به درخواست شماره' }, { v: val('req_no'), w: 10 }, { t: 'مورخ' }, { v: val('req_date'), w: 10 }, { t: 'بدین وسیله ساختمان احداثی در پلاک ثبتی شماره' }, { v: val('plot'), w: 10 },
      { t: 'به نشانی' }, { v: val('address'), w: 18 }, { t: 'دارای پروانه ساختمان شماره' }, { v: val('permit_no'), w: 10 }, { t: 'مورخ' }, { v: val('permit_date'), w: 10 }, { t: 'و طبق گزارش مورخ' }, { v: val('report_date'), w: 10 },
      { t: 'تحت نظارت خانم/آقای' }, { v: val('sup_name'), w: 14 }, { t: 'به شماره امضا' }, { v: val('sup_sign'), w: 10 }, { t: 'و تایید ایشان به شماره برگ' }, { v: val('form_no'), w: 10 },
      { t: 'پایان یافته اعلام گردیده و بهره‌برداری از آن بر اساس مفاد این گواهی پایان ساختمان بلامانع است.' }], XR - 20, XL + 20, 510, 62, 30);
    // limits
    var t0 = 840, cols = [[XR, XR - 150], [XR - 150, XR - 500], [XR - 500, XR - 850]], rh = 66;
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XR - 850, t0, 850, rh * 5); ctx.restore();
    cols.forEach(function (c, i) { if (i) line(c[0], t0, c[0], t0 + rh * 5); });
    txt('ابعاد ملک مطابق سند مالکیت / وضع موجود', (cols[1][0] + cols[1][1]) / 2, t0 + rh / 2, 22, BLACK, 'center', true);
    txt('ابعاد پس از رعایت برهای اصلاحی', (cols[2][0] + cols[2][1]) / 2, t0 + rh / 2, 22, BLACK, 'center', true);
    var names = { north: 'شمالاً', east: 'شرقاً', south: 'جنوباً', west: 'غرباً' };
    ['north', 'east', 'south', 'west'].forEach(function (s, i) {
      var y = t0 + rh * (i + 1); line(XR - 850, y, XR, y);
      txt(names[s], (cols[0][0] + cols[0][1]) / 2, y + rh / 2, 26, BLACK, 'center', true);
      var a = val('sd_' + s + '_deed'), b = val('sd_' + s + '_after');
      if (a !== '') txt(a + ' متر', (cols[1][0] + cols[1][1]) / 2, y + rh / 2, 26, INK, 'center');
      if (b !== '') txt(b + ' متر', (cols[2][0] + cols[2][1]) / 2, y + rh / 2, 26, INK, 'center');
    });
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, t0, 270, 130); ctx.strokeRect(XL, t0 + 160, 270, 130); ctx.restore();
    txt('کاربری زمین', XL + 135, t0 + 28, 24, BLACK, 'center', true); txt(val('use'), XL + 135, t0 + 85, 28, INK, 'center');
    txt('کد', XL + 135, t0 + 188, 24, BLACK, 'center', true); txt(val('code'), XL + 135, t0 + 245, 28, INK, 'center');
    // floors
    var f0 = 1230, fr = 60, tc = [[XR, XR - 270], [XR - 270, XR - 560], [XR - 560, XR - 900], [XR - 900, XL]], rows = data.floors.length + 1;
    var fnames = { basement: 'زیرزمین', ground: 'همکف', mezz: 'نیم‌طبقه', first: 'اول', attic: 'خرپشته' }, heads = ['طبقات', 'مساحت (متر مربع)', 'نوع استفاده', 'تعداد واحد'];
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, f0, XR - XL, fr * rows); ctx.restore();
    tc.forEach(function (c, i) { if (i) line(c[0], f0, c[0], f0 + fr * rows); txt(heads[i], (c[0] + c[1]) / 2, f0 + fr / 2, 23, BLACK, 'center', true); });
    data.floors.forEach(function (fl, r) {
      var y = f0 + fr * (r + 1); line(XL, y, XR, y);
      txt(fnames[fl], (tc[0][0] + tc[0][1]) / 2, y + fr / 2, 25, BLACK, 'center', true);
      var area = val('fl_' + fl + '_area'), use = val('fl_' + fl + '_use'), count = val('fl_' + fl + '_count');
      if (area !== '') txt(area + ' م²', (tc[1][0] + tc[1][1]) / 2, y + fr / 2, 25, INK, 'center');
      if (use !== '') txt(use, (tc[2][0] + tc[2][1]) / 2, y + fr / 2, 25, INK, 'center');
      if (count !== '') txt(count, (tc[3][0] + tc[3][1]) / 2, y + fr / 2, 25, INK, 'center');
    });
    var y = f0 + fr * rows + 60;
    paragraph([{ t: 'این گواهی برای ساختمان مندرج در جدول فوق جمعاً' }, { v: val('floors_count'), w: 6 }, { t: 'طبقه با و بدون زیرزمین با کل زیربنای' }, { v: val('total_area'), w: 8 }, { t: 'متر مربع صادر می‌گردد.' }], XR - 20, XL + 20, y, 58, 29);
    txt('ملاحظات:', XR - 20, y + 110, 28, BLACK, 'right', true);
    paragraph([{ v: val('notes') }], XR - 20, XL + 20, y + 165, 50, 26);
    txt('نام و امضاء دهیار', 360, 1860, 28, BLACK, 'center', true); txt(val('dehyari_name'), 360, 1818, 28, INK, 'center');
    txt('نام و امضاء مسئول فنی دهیاری', 1020, 1860, 28, BLACK, 'center', true); txt(val('tech_name'), 1020, 1818, 28, INK, 'center');
  }

  var form = document.getElementById('pfw-form');
  function read() { form.querySelectorAll('input[name^="f_"]').forEach(function (el) { F[el.name.slice(2)] = el.value; }); }
  form.addEventListener('input', function () { read(); draw(); });
  document.getElementById('pfw-dl').addEventListener('click', async function () {
    var jpg = await PdfLite.toJpeg(canvas); PdfLite.save(PdfLite.make([jpg], W, H), 'endwork-certificate-' + data.file + '.pdf');
  });
  document.getElementById('pfw-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'), im = doc.createElement('img'); doc.title = 'چاپ گواهی پایان ساخت';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}'; doc.head.appendChild(style);
    im.src = canvas.toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); win.focus(); setTimeout(function () { win.print(); }, 400);
  });
  document.fonts.load('30px Vazirmatn').then(function () { return document.fonts.load('bold 30px Vazirmatn'); }).then(function () { document.getElementById('pff-loading').hidden = true; read(); draw(); });
})();
