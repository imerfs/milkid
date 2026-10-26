/* Permit file, step 4: forms 04 (order to prepare the plans), 05 (structure undertaking), 06 (architecture undertaking) and 07
   (supervision undertaking), drawn in the browser from the file's data (json_script #pfd-data) and downloaded as PDF / printed.
   04 and 07 are drawn over their blank forms; 05 and 06 are typeset on the dehyari's blank letterhead. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfd-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREEN = '#0b7a3b', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var page = 'f04', images = {};
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }).replace(/\./g, '٫'); }

  function put(text, box, size) {
    text = fa(text); if (!text) return;
    var x0 = box[0], x1 = box[1], y = box[2], align = box[3], s = size || 30;
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.fillStyle = INK; ctx.font = s + 'px ' + FONT;
    while (ctx.measureText(text).width > (x1 - x0) && s > 14) { s -= 1; ctx.font = s + 'px ' + FONT; }
    ctx.textAlign = align === 'right' ? 'right' : 'center';
    ctx.fillText(text, align === 'right' ? x1 - 4 : (x0 + x1) / 2, y);
  }
  function tick(cx, cy) {
    ctx.save(); ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(cx - 11, cy + 1); ctx.lineTo(cx - 3, cy + 10); ctx.lineTo(cx + 13, cy - 11); ctx.stroke(); ctx.restore();
  }

  // ---------- form 04: the order to prepare the plans ----------
  var ROW = { north: 1195, south: 1257, east: 1319, west: 1381 };
  var TABLE_ROW = { north: 1525, south: 1570, east: 1615, west: 1660 };
  function drawF04() {
    var c = data.common, o = data.order, f = data.forms.f04;
    ctx.drawImage(images.f04, 0, 0, W, H);
    put(f.number, [155, 300, 143, 'right']); put(f.date, [155, 300, 190, 'right']);
    var kind = { construct: [988, 513], demolish: [988, 576], repair: [988, 636] }[o.kind]; if (kind) tick(kind[0], kind[1]);
    put(c.owner, [760, 990, 700, 'center']); put(c.reg_no, [350, 510, 700, 'center']); put(c.lot, [155, 280, 700, 'center']);
    put(o.asli, [1010, 1185, 762, 'center']); put(o.fari, [800, 940, 762, 'center']);
    put(o.lease_no, [425, 570, 762, 'center']); put(o.lease_date, [262, 345, 762, 'center']);
    put(o.request_no, [410, 570, 886, 'center']); put(o.request_date, [155, 340, 886, 'center']);
    tick(o.basis === 'urf' ? 295 : 500, 945);
    if (o.kind === 'construct') tick(1060, 1007);
    put(o.floors, [925, 1030, 1007, 'center']); put(o.floor_area, [435, 570, 1007, 'center']);
    put(c.address, [210, 1075, 1068, 'right'], 28);
    put(o.area ? o.area + ' متر مربع' : '', [880, 1075, 1135, 'right']);
    ['north', 'south', 'east', 'west'].forEach(function (s) {
      var side = (o.sides || {})[s] || {};
      put(side.length ? side.length + ' متر' : '', [880, 1075, ROW[s], 'right']);
      put(side.after ? side.after + ' متر' : '', [735, 1170, TABLE_ROW[s], 'center'], 28);
      put(side.approved ? side.approved + ' متر' : '', [445, 620, TABLE_ROW[s], 'center'], 28);
    });
  }

  // ---------- form 07: the supervision undertaking ----------
  function drawF07() {
    var p = data.people.supervisor, f = data.forms.f07, c = data.common;
    ctx.drawImage(images.f07, 0, 0, W, H);
    put(f.number, [155, 250, 143, 'right']); put(f.date, [155, 430, 188, 'right']);
    put(p.name, [760, 1150, 583, 'center']); put(p.father, [455, 685, 583, 'center']);
    put(p.license, [995, 1170, 652, 'center']);
    put(c.owner, [725, 915, 720, 'center']); put(c.district, [295, 480, 720, 'center']);
  }

  // ---------- forms 05 / 06: a paragraph on the letterhead, the figures inked into it ----------
  function paragraph(parts, x1, x0, y, lineH, size) {
    // parts: [{t: 'template text'} | {v: 'value', w: minimum width of the dotted blank}] in reading order (right to left)
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 18), ink: false, dots: true }); }
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
  function letter(number, date, title, tag) {
    ctx.drawImage(images.letter, 0, 0, W, H);
    ctx.save(); ctx.fillStyle = '#16a34a'; ctx.beginPath(); ctx.roundRect(155, 62, 160, 44, 10); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.font = 'bold 30px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.direction = 'rtl'; ctx.fillText(fa(tag), 235, 86); ctx.restore();
    put(number, [155, 295, 142, 'right']); put(date, [155, 295, 190, 'right']);
    ctx.save(); ctx.fillStyle = GREEN; ctx.font = 'bold 72px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.direction = 'rtl';
    ctx.fillText(title, W / 2, 330); ctx.restore();
  }
  function signatures(leftLines, rightLines, ownerLabel) {
    ctx.save(); ctx.fillStyle = BLACK; ctx.textBaseline = 'middle'; ctx.direction = 'rtl'; ctx.font = 'bold 30px ' + FONT; ctx.textAlign = 'center';
    rightLines.forEach(function (t, i) { ctx.fillText(t, 1000, 1110 + i * 46); });
    leftLines.forEach(function (t, i) { ctx.fillText(t, 370, 1110 + i * 46); });
    ctx.fillText(ownerLabel, 1000, 1470); ctx.fillText('مهر و امضاء دهیار', 370, 1470);
    ctx.restore();
  }
  function drawUndertaking(kind) {
    var c = data.common, f = data.forms[kind], p = data.people[kind === 'f05' ? 'structure' : 'architect'];
    var structure = kind === 'f05';
    letter(f.number, f.date, structure ? 'برگ تعهد محاسبات سازه' : 'برگ تعهد معماری', structure ? 'فرم شماره ۵' : 'فرم شماره ۶');
    var parts = [
      { t: 'اینجانب' }, { v: p.name, w: 22 }, { t: 'فرزند' }, { v: p.father, w: 20 }, { t: 'دارای پرونده اشتغال پایه' }, { v: p.grade, w: 12 },
      { t: 'در رشته' }, { v: p.field, w: 22 }, { t: 'به شماره' }, { v: p.license, w: 22 }, { t: 'صادر از وزارت مسکن و شهرسازی' },
      { t: structure ? 'نقشه‌های اجرایی سازه و دفترچه محاسبات ساختمان' : 'نقشه معماری فاز ۱ و ۲ ساختمان' },
      { t: 'خانم / آقای' }, { v: c.owner, w: 24 }, { t: 'مالک پلاک' }, { v: c.plot, w: 18 }, { t: 'موضوع پرونده کلاسه' }, { v: c.file_class, w: 16 },
      { t: 'با شماره ثبتی' }, { v: c.reg_no, w: 16 },
      { t: structure ? 'را با توجه به ضوابط و آئین نامه ۲۸۰۰ و با رعایت مقررات ملی ساختمان در' : 'را با توجه به ضوابط طرح هادی و با رعایت مقررات ملی ساختمان در' },
      { v: c.floors, w: 12 }, { t: 'سقف و زیربنای' }, { v: c.area, w: 12 }, { t: 'متر مربع انجام داده و' },
      { t: structure ? 'نقشه‌ها و دیتیل‌های اجرایی سازه و دفترچه محاسبات سازه را که پیوست می‌باشد تهیه و مهر و امضاء نموده‌ام.' : 'نقشه‌ها و دیتیل‌های اجرایی مربوطه را به شرح پیوست تهیه و مهر و امضاء نموده‌ام.' },
      { t: 'بدین‌وسیله ضمن تضمین رعایت ضوابط و مقررات فوق‌الذکر در طرح مسئولیت آن را به عهده می‌گیرم.' }
    ];
    paragraph(parts, 1245, 160, 520, 78, 31);
    if (structure) signatures(['محل مهر و امضاء', 'واحد کنترل ظرفیت اشتغال', 'سازمان نظام مهندسی استان'], ['مهر و امضاء', 'مهندس محاسب', 'سازمان نظام مهندسی استان'], 'نام و امضای مالک');
    else signatures(['محل مهر و امضاء واحد کنترل ظرفیت', 'اشتغال به کار سازمان', 'نظام مهندسی استان'], ['محل مهر و امضاء', 'مهندس طراح', 'نقشه‌های معماری'], 'امضاء مالک');
    paragraph([{ t: 'نشانی پلاک:' }, { v: c.address, w: 70 }], 1245, 160, 1300, 56, 28);
  }

  var DRAW = { f04: drawF04, f05: function () { drawUndertaking('f05'); }, f06: function () { drawUndertaking('f06'); }, f07: drawF07 };
  var NAMES = { f04: 'form04-order', f05: 'form05-structure', f06: 'form06-architecture', f07: 'form07-supervision' };
  function draw(which) { page = which || page; ctx.clearRect(0, 0, W, H); DRAW[page](); }
  function pageCanvas(which) { var keep = page; draw(which); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  // ---------- reading the page's inputs so the preview follows what is typed ----------
  function readInputs() {
    document.querySelectorAll('#pfd-people input').forEach(function (el) {
      var m = /^(architect|structure|supervisor)_(\w+)$/.exec(el.name); if (m) data.people[m[1]][m[2]] = el.value;
    });
    document.querySelectorAll('#pfd-forms input, #pfd-forms select').forEach(function (el) {
      var n = el.name, m;
      if ((m = /^c_(\w+)$/.exec(n))) data.common[m[1]] = el.value;
      else if ((m = /^o_(\w+)$/.exec(n))) data.order[m[1]] = el.value;
      else if ((m = /^s_(\w+?)_(\w+)$/.exec(n))) { data.order.sides[m[1]] = data.order.sides[m[1]] || {}; data.order.sides[m[1]][m[2]] = el.value; }
      else if ((m = /^(f0\d)_(number|date)$/.exec(n))) data.forms[m[1]][m[2]] = el.value;
    });
  }
  function refresh() { readInputs(); draw(); }
  ['pfd-people', 'pfd-forms'].forEach(function (id) { var f = document.getElementById(id); f.addEventListener('input', refresh); f.addEventListener('change', refresh); });
  function setTab(which) {
    document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-page') === which); });
    draw(which);
  }
  document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.addEventListener('click', function () { setTab(b.getAttribute('data-page')); }); });

  async function download(list, name) {
    var jpgs = [];
    for (var i = 0; i < list.length; i++) jpgs.push(await PdfLite.toJpeg(pageCanvas(list[i])));
    PdfLite.save(PdfLite.make(jpgs, W, H), name);
  }
  document.getElementById('pfd-dl-this').addEventListener('click', function () { download([page], NAMES[page] + '-' + data.file + '.pdf'); });
  document.getElementById('pfd-dl-all').addEventListener('click', function () { download(['f04', 'f05', 'f06', 'f07'], 'forms04-07-permit-' + data.file + '.pdf'); });
  document.getElementById('pff-print').addEventListener('click', function () {
    var win = window.open('', '_blank'), urls = [];
    ['f04', 'f05', 'f06', 'f07'].forEach(function (w) { urls.push(pageCanvas(w).toDataURL('image/jpeg', 0.92)); });
    var doc = win.document, style = doc.createElement('style');
    doc.title = 'چاپ فرم‌ها';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}';
    doc.head.appendChild(style);
    urls.forEach(function (u) { var im = doc.createElement('img'); im.src = u; doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  function load(src) { return new Promise(function (resolve, reject) { var im = new Image(); im.onload = function () { resolve(im); }; im.onerror = reject; im.src = src; }); }
  Promise.all([load(data.blank.f04), load(data.blank.f07), load(data.blank.letter), document.fonts.load('30px Vazirmatn'), document.fonts.load('bold 30px Vazirmatn')]).then(function (r) {
    images.f04 = r[0]; images.f07 = r[1]; images.letter = r[2];
    document.getElementById('pff-loading').hidden = true;
    refresh();
  });
})();
