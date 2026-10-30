/* Construction without a permit, step 9: form 16 (گزارش تخلف به کمیسیون ماده ۹۹) and the file summary (خلاصه‌ی پرونده, table 5), typeset in the
   browser from the file's data (json_script #f16-data); the preview follows the form; downloaded as PDF or printed. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('f16-data').textContent), v = data.v;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREY = '#6b7280', FONT = 'Vazirmatn, Tahoma, sans-serif', FA = '۰۱۲۳۴۵۶۷۸۹', page = data.part || 'form16';
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }
  function label(list, key) { var f = list.filter(function (p) { return p[0] === key; })[0]; return f ? f[1] : ''; }

  function text(t, x, y, size, o) {
    o = o || {};
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = o.align || 'right';
    ctx.fillStyle = o.color || BLACK; ctx.font = (o.bold ? 'bold ' : '') + size + 'px ' + FONT; ctx.fillText(t, x, y);
  }
  function words(parts) {
    var out = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) out.push({ text: w }); });
      else { var s = fa(p.v); if (s) s.split(' ').forEach(function (w) { out.push({ text: w, ink: true }); }); else out.push({ text: '.'.repeat(p.w || 12), dots: true }); }
    });
    return out;
  }
  function paragraph(parts, x1, x0, y, lineH, size) {
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var x = x1, line = y, space = size * 0.3;
    words(parts).forEach(function (w) {
      ctx.font = (w.ink ? 'bold ' : '') + size + 'px ' + FONT;
      var width = ctx.measureText(w.text).width;
      if (x - width < x0) { x = x1; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? GREY : BLACK); ctx.fillText(w.text, x, line); x -= width + space;
    });
    return line;
  }
  function blank() { ctx.clearRect(0, 0, W, H); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); }
  function circle(x, y, on) { ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 12, 0, 7); ctx.stroke(); if (on) { ctx.fillStyle = INK; ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fill(); } }
  // a row of options, each a label then its circle, wrapped from the right edge
  function options(list, selected, x1, x0, y, size, lineH) {
    ctx.font = size + 'px ' + FONT; ctx.direction = 'rtl'; var x = x1, line = y;
    list.forEach(function (o) {
      var w = ctx.measureText(o[1]).width + 50;
      if (x - w < x0) { x = x1; line += lineH; }
      text(o[1], x, line, size); circle(x - ctx.measureText(o[1]).width - 24, line, selected.indexOf(o[0]) >= 0); x -= w + 18;
    });
    return line;
  }

  function drawForm16() {
    blank();
    text('فرم شماره ۱۶', 1330, 60, 30, { bold: true });
    text('شماره: ' + fa(v.number), 380, 70, 26, { color: INK, bold: true }); text('تاریخ: ' + fa(v.date), 380, 120, 26, { color: INK, bold: true });
    text('بسمه تعالی', W / 2, 190, 32, { bold: true, align: 'center' });
    text('گزارش تخلف به کمیسیون ماده ۹۹', W / 2, 260, 46, { bold: true, align: 'center' });
    var y = paragraph([{ t: 'در بازدید مورخ' }, { v: v.visit_date, w: 10 }, { t: 'مشاهده گردید مالک بنای احداثی آقای/ خانم' }, { v: v.owner, w: 16 }, { t: 'واقع در روستای' }, { v: v.village, w: 10 },
      { t: 'دهستان' }, { v: v.dehestan, w: 10 }, { t: 'بخش' }, { v: v.district, w: 10 }, { t: 'که کاربری زمین نامبرده:' }], 1330, 80, 360, 62, 28);
    y = options(data.uses, [v.use], 1330, 80, y + 62, 27, 56);
    text('می‌باشد:', 120, y, 27);
    y += 70; text('الف - ساختمان را بدون اخذ پروانه:', 1330, y, 27, { bold: true });
    options(data.built, [v.built], 800, 80, y, 27, 56);
    y += 76; text('ب - ساختمان را با اخذ پروانه ساختمانی احداث کرده ولی موارد ذیل رعایت نگردیده است:', 1330, y, 27, { bold: true });
    y += 62; text('۱ - عدم رعایت عقب‌نشینی درنظر گرفته شده برای:', 1330, y, 25);
    y = options(data.setbacks, v.b1, 1330, 80, y + 52, 24, 52);
    data.others.forEach(function (o, i) {
      y += 54; text(fa(i + 2) + ' - ' + o[1] + (o[0] === 'b5' && v.b5_area ? ' به متراژ ' + fa(v.b5_area) + ' مترمربع' : ''), 1300, y, 24); circle(100, y, v.b.indexOf(o[0]) >= 0);
    });
    y += 54; text('۹ - کروکی محل', 1330, y, 24);
    if (v.notes) text(fa(v.notes), 700, y + 70, 28, { color: INK, bold: true, align: 'center' });
    y = Math.max(y + 140, 1170);
    text('لذا با توجه به توضیحات فوق الذکر:', 1330, y, 26, { bold: true });
    data.requests.forEach(function (r, i) { var yy = y + 56 + i * 56; text(r[1], 1300, yy, 25); circle(100, yy, v.requests.indexOf(r[0]) >= 0); });
    y += 56 + data.requests.length * 56 + 10;
    y = paragraph([{ t: 'ضمناً برگ اخطار شماره' }, { v: v.notice_no, w: 10 }, { t: 'به تاریخ' }, { v: v.notice_date, w: 10 }], 1330, 80, y, 52, 26);
    y = options(data.served, v.served, 1330, 80, y + 56, 24, 52);
    text('نام و نام خانوادگی بخشدار', 1000, 1790, 24, { bold: true, align: 'center' }); text(fa(v.governor), 1000, 1830, 26, { color: INK, bold: true, align: 'center' });
    text('امضاء', 1000, 1870, 22, { color: GREY, align: 'center' });
    text('نام و نام خانوادگی دهیار', 330, 1790, 24, { bold: true, align: 'center' }); text(fa(v.dehyar), 330, 1830, 26, { color: INK, bold: true, align: 'center' });
    text('امضاء و مهر', 330, 1870, 22, { color: GREY, align: 'center' });
  }

  function drawSummary() {
    var s = v.summary;
    blank();
    text('(جدول شماره ۵)', W / 2, 70, 26, { bold: true, align: 'center' });
    text('شماره: ' + fa(s.number), 330, 150, 28, { color: INK, bold: true }); text('تاریخ: ' + fa(s.date), 330, 205, 28, { color: INK, bold: true });
    text('خلاصه پرونده', W / 2, 160, 50, { bold: true, align: 'center' }); text('(داخل محدوده روستاها)', W / 2, 235, 28, { bold: true, align: 'center' });
    text('بسمه تعالی', W / 2, 360, 30, { bold: true, align: 'center' });
    text('اعضاء محترم کمیسیون تبصره ۲ بند ۳ ماده ۹۹ قانون شهرداریها', 1330, 450, 36, { bold: true });
    text('سلام علیکم', 1330, 540, 28, { bold: true });
    var y = paragraph([{ t: 'با احترام، به پیوست پرونده آقای' }, { v: v.owner, w: 16 }, { t: 'فرزند' }, { v: v.father, w: 10 }, { t: 'با شماره' }, { v: v.phone, w: 11 },
      { t: 'ساکن روستای' }, { v: v.village, w: 10 }, { t: 'بخش' }, { v: v.district, w: 10 }, { t: 'شهرستان' }, { v: v.county, w: 10 },
      { t: 'که جمعاً به میزان' }, { v: s.area, w: 8 }, { t: 'مترمربع بنای ' + (s.use || 'مسکونی') + ' (بدون پروانه) و بصورت غیر مجاز احداث نموده است و استحکام بنای آن توسط جناب آقای مهندس' },
      { v: s.expert, w: 16 }, { t: 'با شماره نامه' }, { v: s.expert_no, w: 8 }, { t: 'مورخ' }, { v: s.expert_date, w: 10 }, { t: 'و نوع سازه' }, { v: s.structure, w: 10 },
      { t: 'و سال ساخت' }, { v: s.year, w: 6 }, { t: 'برای استفاده ' + (s.use || 'مسکونی') + ' تائید (' + (s.strength === 'lacks' ? 'نشده' : 'شده') + ') است، برای استحضار و طرح در کمیسیون تبصره ۲ بند ۳ ماده ۹۹ تقدیم می‌گردد.' }],
      1330, 80, 660, 70, 29);
    text('ضمنا ملک مورد نظر در تعریض ' + (s.widening ? 'می‌باشد' : 'نمی‌باشد') + '.', 1330, y + 100, 29, { bold: true });
    text('نام و نام خانوادگی مسئول: ' + fa(v.dehyar), 1330, 1260, 28, { bold: true });
    text('امضاء دهیار / بخشدار / فرماندار', 1000, 1350, 28, { bold: true });
    text('شماره تماس مسئول مطلع از جریان پرونده: ' + fa(s.contact), 1330, 1470, 28, { bold: true });
  }

  function draw() { if (page === 'form16') drawForm16(); else drawSummary(); }
  var form = document.getElementById('f16-form');
  function read() {
    var f = form.elements, s = v.summary;
    ['number', 'date', 'visit_date', 'owner', 'father', 'national_id', 'village', 'dehestan', 'district', 'county', 'phone', 'b5_area', 'notice_no', 'notice_date', 'notes', 'dehyar', 'governor'].forEach(function (k) { if (f[k]) v[k] = f[k].value; });
    var map = { s_number: 'number', s_date: 'date', s_area: 'area', s_expert: 'expert', s_expert_no: 'expert_no', s_expert_date: 'expert_date', s_structure: 'structure', s_year: 'year', s_contact: 'contact', s_strength: 'strength' };
    Object.keys(map).forEach(function (k) { if (f[k]) s[map[k]] = f[k].value; });
    s.widening = !!(f.s_widening && f.s_widening.checked);
    var use = form.querySelector('input[name=use]:checked'); if (use) { v.use = use.value; s.use = label(data.uses, use.value); }
    var built = form.querySelector('input[name=built]:checked'); if (built) v.built = built.value;
    ['b1', 'b', 'requests', 'served'].forEach(function (name) { v[name] = Array.prototype.map.call(form.querySelectorAll('input[name=' + name + ']:checked'), function (el) { return el.value; }); });
    draw();
  }
  form.addEventListener('input', read); form.addEventListener('change', read);
  var tabs = document.getElementById('f16-tabs');
  tabs.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () {
    page = b.getAttribute('data-page'); tabs.querySelectorAll('button').forEach(function (x) { x.classList.toggle('is-on', x === b); }); draw(); }); });
  function pageCanvas() { var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); return c; }
  document.getElementById('f16-dl').addEventListener('click', async function () {
    PdfLite.save(PdfLite.make([await PdfLite.toJpeg(pageCanvas())], W, H), (page === 'form16' ? 'form-16-' : 'file-summary-') + data.file + '.pdf');
  });
  document.getElementById('f16-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'), im = doc.createElement('img');
    doc.title = 'چاپ'; style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}';
    doc.head.appendChild(style); im.src = pageCanvas().toDataURL('image/jpeg', 0.92); doc.body.appendChild(im);
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });
  Promise.all([document.fonts.load('26px Vazirmatn'), document.fonts.load('bold 26px Vazirmatn')]).then(function () { document.getElementById('pff-loading').hidden = true; read(); });
})();
