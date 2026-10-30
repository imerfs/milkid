/* Construction without a permit, step 4: the technical expert's visit report (گزارش بازدید) and, for a building with an overhang over the
   street, the owner's request and the dehyari's letter to the electricity distribution office. Typeset in the browser from the file's
   data (json_script #prp-data); the preview follows the form; downloaded as PDF or printed. The sums are worked out here exactly as
   main/office/permit_report.py does. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('prp-data').textContent);
  var v = data.v;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREY = '#6b7280', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var R = 1330, L = 70, FA = '۰۱۲۳۴۵۶۷۸۹', page = 'report';
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }
  function n(s) { var x = parseFloat(String(s == null ? '' : s).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/٫/g, '.').replace(/,/g, '.')); return isFinite(x) ? x : 0; }
  function r2(x) { x = Math.round(x * 100) / 100; return String(x); }

  function totals() {
    var out = { floors: {}, total: 0, units: 0, over: 0 };
    data.floors.forEach(function (f) {
      var k = f[0], p = v.floors[k], res = n(p.res) + n(p.over_yard) * 2 / 3 + n(p.yard);
      var t = res + n(p.commercial) + n(p.parking) + n(p.pilotis) + n(p.storage) + n(p.penthouse) + n(p.overhang);
      out.floors[k] = { res: res, total: t }; out.total += t; out.units += Math.floor(n(p.units)); out.over += n(p.overhang);
    });
    out.excess = out.total - n(v.permit_area) - n(v.ruling_area);
    out.occupation = n(v.existing_area) ? out.floors.ground.total * 100 / n(v.existing_area) : 0;
    out.separation = n(v.existing_area) >= 160;
    return out;
  }

  // ---------- helpers ----------
  function text(t, x, y, size, o) {
    o = o || {};
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = o.align || 'right';
    ctx.fillStyle = o.color || BLACK; ctx.font = (o.bold ? 'bold ' : '') + size + 'px ' + FONT;
    var s = size; while (o.max && ctx.measureText(t).width > o.max && s > 12) { s -= 1; ctx.font = (o.bold ? 'bold ' : '') + s + 'px ' + FONT; }
    ctx.fillText(t, x, y);
  }
  function box(x, y, w, h) { ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.strokeRect(x, y, w, h); }
  function cell(x, y, w, h, label, value, unit) {                    // (x, y) is the top-left corner
    box(x, y, w, h);
    ctx.direction = 'rtl'; ctx.font = 'bold 24px ' + FONT;
    var lw = ctx.measureText(label).width;
    text(label, x + w - 10, y + h / 2, 24, { bold: true });
    text(fa(value) + (unit ? ' ' + unit : ''), x + w - 10 - lw - 12, y + h / 2, 26, { color: INK, bold: true, max: w - lw - 30 });
  }
  function para(parts, y, lineH, size, right, left) {
    right = right || R; left = left || L + 20;
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var s = fa(p.v); if (s) s.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 14), dots: true }); }
    });
    var x = right, line = y, space = size * 0.3;
    words.forEach(function (w) {
      ctx.font = (w.ink ? 'bold ' : '') + size + 'px ' + FONT;
      var width = ctx.measureText(w.text).width;
      if (x - width < left) { x = right; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? GREY : BLACK); ctx.fillText(w.text, x, line); x -= width + space;
    });
    return line;
  }
  function blankPage() { ctx.clearRect(0, 0, W, H); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); }
  function frame() { ctx.strokeStyle = BLACK; ctx.lineWidth = 10; ctx.strokeRect(60, 50, W - 120, H - 100); ctx.lineWidth = 3; ctx.strokeRect(82, 72, W - 164, H - 144); }

  // ---------- the visit report ----------
  function drawReport() {
    var t = totals(), w3 = (R - L) / 3;
    blankPage();
    text('دهیاری ' + fa(data.power.village), R, 80, 38, { bold: true });
    text('گزارش بازدید', W / 2, 95, 52, { bold: true, align: 'center' });
    text('شماره: ' + fa(v.number), 380, 70, 28, { color: INK, bold: true, align: 'right' });
    text('تاریخ: ' + fa(v.date), 380, 120, 28, { color: INK, bold: true, align: 'right' });
    var y = 180, h = 66;
    [[['نام مالک:', v.name], ['نام پدر:', v.father], ['کاربری ملک:', v.land_use]],
     [['شماره ملی:', v.national_id], ['شماره تماس:', v.phone], ['وضعیت:', v.status]],
     [['مجموع زیربنا:', r2(t.total), 'م²'], ['با پروانه:', v.permit_area], ['بارای کمیسیون:', v.ruling_area]],
     [['مازاد / فاقد (رای - پروانه):', r2(t.excess), 'م²'], ['تاریخ پروانه:', v.permit_date], ['تاریخ رای:', v.ruling_date]],
     [['سال ساخت:', v.year], ['نوع سقف:', v.roof], ['نوع سازه:', v.structure]]].forEach(function (row) {
      row.forEach(function (c, i) { cell(R - (i + 1) * w3, y, w3, h, c[0], c[1], c[2]); }); y += h;
    });
    cell(R - w3 * 2, y, w3 * 2, h, 'آدرس:', v.address); cell(L, y, w3, h, 'مختصات:', (v.utm_x ? 'X=' + v.utm_x : '') + ' ' + (v.utm_y ? 'Y=' + v.utm_y : ''));
    y += h + 30;
    // limits
    var cols = [150, 300, 260, 220, 330], x = R;
    ['حدود ملک', 'حدفاصل مجاور', 'ابعاد موجود', 'عرض معبر', 'ابعاد بعد از رعایت برهای اصلاحی'].forEach(function (hd, i) {
      box(x - cols[i], y, cols[i], 64); text(hd, x - cols[i] / 2, y + 32, 22, { bold: true, align: 'center', max: cols[i] - 14 }); x -= cols[i];
    });
    y += 64;
    data.sides.forEach(function (s) {
      var l = v.limits[s[0]], vals = [s[1], l.adjacent, l.existing, l.passage, l.after]; x = R;
      vals.forEach(function (c, i) { box(x - cols[i], y, cols[i], 56); text(fa(c), x - cols[i] / 2, y + 28, 26, { bold: true, align: 'center', color: i ? INK : BLACK, max: cols[i] - 14 }); x -= cols[i]; });
      y += 56;
    });
    y += 30;
    cell(R - w3, y, w3, h, 'مساحت طبق سند:', v.deed_area, 'م²'); cell(R - 2 * w3, y, w3, h, 'مساحت وضع موجود:', v.existing_area, 'م²');
    cell(L, y, w3, h, 'مساحت پس از اصلاح:', v.after_area, 'م²'); y += h;
    cell(R - w3, y, w3, h, 'سطح اشغال (درصد):', r2(t.occupation)); cell(R - 2 * w3, y, w3, h, 'حد مجاز تفکیک:', t.separation ? 'رعایت شده است' : 'رعایت نشده است');
    cell(L, y, w3, h, 'پارکینگ مورد نیاز / تأمین‌شده:', t.units + ' / ' + n(v.parking_provided)); y += h + 30;
    // floors
    var fc = [110, 80, 140, 125, 125, 110, 110, 110, 150, 100, 100]; x = R;
    ['طبقه', 'واحد', 'مسکونی', 'تجاری', 'پارکینگ', 'پیلوت', 'انباری', 'خرپشته', 'پیش‌آمدگی به معبر', 'ارتفاع', 'مجموع'].forEach(function (hd, i) {
      box(x - fc[i], y, fc[i], 70); text(hd, x - fc[i] / 2, y + 35, 21, { bold: true, align: 'center', max: fc[i] - 10 }); x -= fc[i];
    });
    y += 70;
    data.floors.forEach(function (f) {
      var p = v.floors[f[0]], tt = t.floors[f[0]];
      var vals = [f[1], p.units, r2(tt.res), p.commercial, p.parking, p.pilotis, p.storage, p.penthouse, p.overhang, p.height, r2(tt.total)]; x = R;
      vals.forEach(function (c, i) { box(x - fc[i], y, fc[i], 54); text(i === 0 ? c : (n(c) ? fa(c) : ''), x - fc[i] / 2, y + 27, 24, { bold: true, align: 'center', color: i ? INK : BLACK, max: fc[i] - 10 }); x -= fc[i]; });
      y += 54;
    });
    x = R;
    ['جمع', t.units, '', '', '', '', '', '', r2(t.over), '', r2(t.total)].forEach(function (c, i) { box(x - fc[i], y, fc[i], 54); text(fa(c), x - fc[i] / 2, y + 27, 24, { bold: true, align: 'center', color: i ? INK : BLACK }); x -= fc[i]; });
    y += 104;
    // notes
    text('توضیحات:', R, y, 28, { bold: true }); y += 46;
    var yard = data.floors.map(function (f) { return n(v.floors[f[0]].yard); }).reduce(function (a, b) { return a + b; }, 0);
    var notes = ['کروکی نقشه در پشت برگه پیوست گردیده.', 'ضوابط و مقررات ساختمانی به شرح ذیل می‌باشد:',
      '• در صورتی که عرض حیاط خلوت کمتر از ۲ متر (سرتاسر) یا مساحت آن کمتر از ۱۲ مترمربع باشد، مساحت مورد نظر در سطح اشغال و تراکم لحاظ می‌شود (حیاط خلوت محاسبه‌شده: ' + fa(r2(yard)) + ' مترمربع).',
      '• در صورتی که پیش‌آمدگی دو طرف یا سه طرف بسته باشد، ۲/۳ مساحت آن جزء زیربنا لحاظ می‌شود.'];
    if (v.notes) notes.push(v.notes);
    notes.forEach(function (s) { y = para([{ t: s }], y, 38, 23, R, L + 20) + 42; });
    y = Math.max(y + 10, 1740);
    para([{ t: 'این گواهی دال بر مالکیت نمی‌باشد. ضمنا اطلاعات مذکور صرفا جهت ارائه به کمیسیون ماده ۹۹ بوده و بر اساس طرح هادی مصوب فعلی روستا بوده و قابل بهره‌برداری در هیچ موضوع دیگری نمی‌باشد و از تاریخ ذکرشده به مدت سه ماه دارای اعتبار می‌باشد.' }], y, 36, 22, R, L + 20);
    text('مسئول فنی دهیاری', 420, 1895, 28, { bold: true, align: 'center' }); text(fa(v.signer), 420, 1940, 28, { color: INK, bold: true, align: 'center' });
  }

  // ---------- the letters about an overhang ----------
  function powerRows() {
    var rows = [];
    data.sides.forEach(function (s) {
      var oh = (v.overhang_rows || {})[s[0]] || {}, lim = v.limits[s[0]] || {};
      if (oh.balcony || oh.passage || lim.adjacent === 'معبر') rows.push({ side: s[1], passage: oh.passage || lim.passage || '', sidewalk: oh.sidewalk || '', balcony: oh.balcony || '', network: oh.network || '' });
    });
    return rows;
  }
  function drawRequest() {
    blankPage(); frame();
    text('بسمه تعالی', W / 2, 140, 40, { bold: true, align: 'center' });
    text('«فرم درخواست»', 1235, 270, 52, { bold: true }); text('تاریخ: ' + fa(v.date), 400, 270, 34, { color: INK, bold: true, align: 'left' });
    text('دهیاری روستای ' + fa(data.power.village), 1235, 430, 44, { bold: true }); text('باسلام', 1235, 520, 34);
    var y = para([{ t: 'اینجانب' }, { v: v.name, w: 22 }, { t: 'فرزند' }, { v: v.father, w: 14 }, { t: 'با شماره ملی' }, { v: v.national_id, w: 12 },
      { t: 'ساکن روستای' }, { v: data.power.village, w: 10 }, { t: '، آدرس' }, { v: v.address, w: 30 }], 610, 82, 34, 1235, 165);
    y = para([{ t: 'تقاضای' }, { v: v.overhang_built ? 'تایید پیش‌آمدگی احداث‌شده' : 'مجوز احداث پیش‌آمدگی' }, { t: 'ملک خود روی معبر و ارسال نامه به اداره برق شهرستان بیرجند را دارم. خواهشمند است در صورت امکان مساعدت فرمایید.' }], y + 110, 82, 34, 1235, 165);
    y = para([{ t: 'تلفن تماس:' }, { v: v.phone, w: 24 }], y + 100, 82, 34, 1235, 165);
    text('امضاء و اثرانگشت متقاضی', 1235, y + 140, 32, { bold: true });
  }
  function drawLetter() {
    blankPage();
    text('بسمه تعالی', W / 2, 90, 36, { bold: true, align: 'center' });
    text('شماره: ........................', 300, 150, 28, { align: 'right' }); text('تاریخ: ' + fa(v.date), 300, 200, 28, { align: 'right', color: INK, bold: true });
    text('مدیریت محترم توزیع نیروی برق شهرستان بیرجند', R, 300, 38, { bold: true });
    text('با سلام و احترام؛', R, 370, 32);
    var y = para([{ t: 'به پیوست تصویر نامه' }, { t: v.father ? 'آقای/خانم' : 'آقای/خانم' }, { v: v.name, w: 20 }, { t: 'فرزند' }, { v: v.father, w: 12 },
      { t: 'مبنی بر ' + (v.overhang_built ? 'تائید پیش‌آمدگی احداث‌شده' : 'درخواست احداث پیش‌آمدگی') + ' ملک در' }, { v: v.address, w: 26 },
      { t: 'ارسال می‌گردد، خواهشمند است اعلام نظر نمائید. ضمنا مشخصات معابر ملک مذکور به شرح ذیل اعلام می‌گردد:' }], 450, 66, 31, R, 120);
    y += 70;
    var cols = [180, 220, 330, 330, 240], x = R, heads = ['معبر ضلع', 'عرض معبر / متر', 'عرض مفید پیاده‌روی موجود / متر', 'میزان بالکن (با احتساب نماسازی یا بدون نما) / متر', 'فاصله از شبکه موجود / متر'];
    heads.forEach(function (hd, i) { box(x - cols[i], y, cols[i], 120); para([{ t: hd }], y + 30, 30, 22, x - 8, x - cols[i] + 8); x -= cols[i]; });
    y += 120;
    var rows = powerRows(); if (!rows.length) rows = [{ side: '', passage: '', sidewalk: '', balcony: '', network: '' }];
    rows.forEach(function (r) {
      var vals = [r.side ? r.side + ' ملک' : '', r.passage, r.sidewalk, r.balcony, r.network]; x = R;
      vals.forEach(function (c, i) { box(x - cols[i], y, cols[i], 70); text(fa(c), x - cols[i] / 2, y + 35, 28, { align: 'center', bold: true, color: INK }); x -= cols[i]; });
      y += 70;
    });
    if (data.power.utm) text(data.power.utm, R, y + 60, 28, { color: INK, bold: true });
    text('با تشکر', 700, y + 180, 32, { bold: true, align: 'center' });
    text('دهیار دستگرد', 330, y + 250, 34, { bold: true, align: 'center' });
    text('مهر و امضاء', 330, y + 300, 26, { color: GREY, align: 'center' });
  }

  var DRAW = { report: drawReport, request: drawRequest, letter: drawLetter };
  var NAMES = { report: 'visit-report', request: 'electricity-request', letter: 'electricity-letter' };
  function draw(which) { page = which || page; DRAW[page](); }
  function pageCanvas() { var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); return c; }

  // ---------- the form feeds the preview ----------
  var form = document.getElementById('prp-form');
  function read() {
    if (form) {
      var f = form;
      ['number', 'date', 'visit_date', 'name', 'father', 'national_id', 'phone', 'land_use', 'status', 'address', 'utm_x', 'utm_y', 'permit_area', 'permit_date', 'permit_no',
        'ruling_area', 'ruling_date', 'ruling_no', 'year', 'roof', 'structure', 'deed_area', 'existing_area', 'after_area', 'parking_provided', 'notes', 'signer'].forEach(function (k) {
        var el = f.elements[k]; if (el) v[k] = el.value;
      });
      data.sides.forEach(function (s) {
        ['adjacent', 'existing', 'passage', 'after'].forEach(function (k) { var el = f.elements[s[0] + '_' + k]; if (el) v.limits[s[0]][k] = el.value; });
        ['passage', 'sidewalk', 'balcony', 'network'].forEach(function (k) { var el = f.elements['oh_' + s[0] + '_' + k]; if (el) v.overhang_rows[s[0]][k] = el.value; });
      });
      data.floors.forEach(function (fl) {
        ['units', 'res', 'commercial', 'parking', 'penthouse', 'overhang', 'pilotis', 'storage', 'height', 'over_yard', 'yard'].forEach(function (k) {
          var el = f.elements[fl[0] + '_' + k]; if (el) v.floors[fl[0]][k] = el.value;
        });
      });
      var built = f.querySelector('input[name=overhang_built]:checked'); if (built) v.overhang_built = built.value === 'built';
    }
    draw();
  }
  if (form) { form.addEventListener('input', read); form.addEventListener('change', read); }
  function setTab(which) { document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-page') === which); }); draw(which); }
  document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.addEventListener('click', function () { setTab(b.getAttribute('data-page')); }); });

  document.getElementById('prp-dl').addEventListener('click', async function () {
    PdfLite.save(PdfLite.make([await PdfLite.toJpeg(pageCanvas())], W, H), NAMES[page] + '-' + data.file + '.pdf');
  });
  document.getElementById('prp-print').addEventListener('click', function () {
    var win = window.open('', '_blank'), doc = win.document, style = doc.createElement('style'), im = doc.createElement('img');
    doc.title = 'چاپ'; style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}';
    doc.head.appendChild(style); im.src = pageCanvas().toDataURL('image/jpeg', 0.92); doc.body.appendChild(im);
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  Promise.all([document.fonts.load('26px Vazirmatn'), document.fonts.load('bold 26px Vazirmatn')]).then(function () {
    document.getElementById('pff-loading').hidden = true; read();
  });
})();
