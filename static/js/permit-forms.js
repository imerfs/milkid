/* Permit file, step 2: draws form 1, the plot map and form 2 over the blank forms and downloads them as a PDF.
   Drawing happens in the browser (it shapes Persian text); the server only supplies the data (json_script #pff-data). */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pff-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var f1 = data.form1, f2 = data.form2, page = 'f1';
  var images = {};

  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(text) { return String(text == null ? '' : text).replace(/\d/g, function (d) { return FA[d]; }).replace(/\./g, '٫'); }
  function num(text) { return String(text == null ? '' : text).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }); }

  // ---------- where each value goes on the blank forms (pixels of the 1400 x 2000 images; y is the text's middle) ----------
  var F1 = {
    number: [157, 388, 142, 'right'], date: [158, 440, 188, 'right'], bonyad_city: [530, 740, 490, 'center'],
    request_no: [790, 1050, 735, 'center'], request_date: [440, 715, 735, 'center'],
    name: [840, 1000, 783, 'center'], father: [570, 760, 783, 'center'], id_number: [165, 350, 783, 'center'],
    issued_at: [830, 1050, 831, 'center'], national_id: [350, 560, 831, 'center'], wakalat_no: [630, 790, 880, 'center'],
    plot: [575, 655, 928, 'center'], area: [170, 480, 928, 'center'],
    village: [725, 875, 977, 'center'], district: [500, 660, 977, 'center'], county: [170, 370, 977, 'center']
  };
  var F1_LIMITS = { north: 1355, south: 1405, west: 1497, east: 1547 };
  var F2 = {
    number: [150, 245, 144, 'right'], date: [150, 420, 188, 'right'],
    name: [885, 1125, 503, 'center'], father: [680, 815, 503, 'center'], id_number: [305, 450, 503, 'center'], issued_at: [95, 185, 503, 'center'],
    village: [815, 1055, 568, 'center'], dehestan: [360, 715, 568, 'center'], district: [100, 300, 568, 'center'],
    area: [655, 810, 635, 'center'],
    section: [905, 1055, 955, 'center'], plot: [700, 805, 955, 'center'], qate: [440, 570, 955, 'center'], asli: [305, 365, 955, 'center'], fari: [205, 300, 955, 'center'],
    exact_address: [175, 840, 1005, 'right'],
    lease_no: [775, 960, 1188, 'center'], lessor: [455, 660, 1188, 'center'], lease_date: [140, 300, 1188, 'center'],
    rep_name: [800, 1005, 1348, 'center'], rep_father: [575, 720, 1348, 'center'], rep_id: [175, 360, 1348, 'center'], rep_issued: [1095, 1215, 1405, 'center']
  };
  var F2_PURPOSE = { demolition: [335, 697], repair: [131, 697], construction: [1089, 762] };
  var F2_ATTACH = { attach1: [869, 1615], attach2: [381, 1658], attach3: [637, 1793], attach4: [450, 1832] };

  function put(text, box, size) {
    text = fa(text);
    if (!text) return;
    var x0 = box[0], x1 = box[1], y = box[2], align = box[3], s = size || 30;
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.fillStyle = INK;
    ctx.font = s + 'px ' + FONT;
    while (ctx.measureText(text).width > (x1 - x0) && s > 15) { s -= 1; ctx.font = s + 'px ' + FONT; }
    ctx.textAlign = align === 'right' ? 'right' : 'center';
    ctx.fillText(text, align === 'right' ? x1 - 4 : (x0 + x1) / 2, y);
  }
  function tick(cx, cy) {
    ctx.save(); ctx.strokeStyle = INK; ctx.lineWidth = 6; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(cx - 11, cy + 1); ctx.lineTo(cx - 3, cy + 10); ctx.lineTo(cx + 13, cy - 11); ctx.stroke(); ctx.restore();
  }
  function stamp(text) {       // a faint «draft» mark until the form is saved
    ctx.save(); ctx.globalAlpha = 0.10; ctx.fillStyle = '#b91c1c'; ctx.font = 'bold 190px ' + FONT; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.translate(W / 2, H / 2); ctx.rotate(-0.6); ctx.fillText(text, 0, 0); ctx.restore();
  }

  function drawForm1() {
    ctx.drawImage(images.f1, 0, 0, W, H);
    Object.keys(F1).forEach(function (k) {
      var text = f1[k];
      if (k === 'area' && text) text = text + ' متر مربع';
      put(text, F1[k]);
    });
    var addr = String(f1.address || ''), words = addr.split(' '), first = '', rest = [];
    ctx.font = '28px ' + FONT;
    words.forEach(function (w) { var t = first ? first + ' ' + w : w; if (!rest.length && ctx.measureText(fa(t)).width <= 420) first = t; else rest.push(w); });
    put(first, [600, 1025, 1025, 'right'], 28);
    if (rest.length) put(rest.join(' '), [185, 425, 1025, 'right'], 26);
    Object.keys(F1_LIMITS).forEach(function (side) {
      var lim = (f1.limits || {})[side] || {}, y = F1_LIMITS[side];
      if (Number(num(lim.length)) > 0) put(String(lim.length), [862, 985, y, 'center']);
      put(lim.to, [180, 700, y, 'right'], 28);
    });
    if (!data.form1_saved) stamp('پیش‌نویس');
  }

  function drawForm2() {
    ctx.drawImage(images.f2, 0, 0, W, H);
    var DEED = ['section', 'plot', 'qate', 'asli', 'fari', 'exact_address'], LEASE = ['lease_no', 'lessor', 'lease_date'];
    Object.keys(F2).forEach(function (k) {
      // only the box of the paper the owner has: a deed (or agreement) or a Bonyad contract
      if (f2.ownership === 'bonyad' ? DEED.indexOf(k) >= 0 : LEASE.indexOf(k) >= 0) return;
      var text = f2[k];
      if (k === 'area' && text) text = text + ' متر';
      put(text, F2[k]);
    });
    var c = F2_PURPOSE[f2.purpose]; if (c) tick(c[0], c[1]);
    Object.keys(F2_ATTACH).forEach(function (k) { if (f2[k]) tick(F2_ATTACH[k][0], F2_ATTACH[k][1]); });
    if (!data.form2_saved) stamp('پیش‌نویس');
  }

  // ---------- the plot map (page 2 of form 1) ----------
  function drawSheet() {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#0f766e'; ctx.lineWidth = 6; ctx.strokeRect(40, 40, W - 80, H - 80);
    ctx.fillStyle = INK; ctx.direction = 'rtl'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = 'bold 54px ' + FONT; ctx.fillText('نقشه‌ی ملک', W / 2, 120);
    ctx.font = '30px ' + FONT;
    ctx.fillText(fa('ضمیمه‌ی فرم شماره ۱ — ' + (f1.number || '') + ' — ' + (f1.date || '')), W / 2, 180);
    var sh = data.sheet, box = { x: 90, y: 240, w: W - 180, h: 1260 };
    ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 2; ctx.strokeRect(box.x, box.y, box.w, box.h);
    if (!sh) {
      ctx.fillStyle = '#64748b'; ctx.font = '32px ' + FONT; ctx.fillText('نقشه‌ی این ملک هنوز در سامانه نیست (کد نوسازی به قطعه‌ی نقشه وصل نشده).', W / 2, box.y + box.h / 2);
    } else {
      var minx = 1e9, miny = 1e9, maxx = -1e9, maxy = -1e9;
      sh.plot.forEach(function (p) { minx = Math.min(minx, p[0]); maxx = Math.max(maxx, p[0]); miny = Math.min(miny, p[1]); maxy = Math.max(maxy, p[1]); });
      var pad = 22;                                   // metres of surroundings shown around the plot
      minx -= pad; maxx += pad; miny -= pad; maxy += pad;
      var k = Math.min((box.w - 40) / (maxx - minx), (box.h - 40) / (maxy - miny));
      var ox = box.x + box.w / 2 - k * (minx + maxx) / 2, oy = box.y + box.h / 2 + k * (miny + maxy) / 2;
      var X = function (p) { return ox + p[0] * k; }, Y = function (p) { return oy - p[1] * k; };
      ctx.save(); ctx.beginPath(); ctx.rect(box.x + 1, box.y + 1, box.w - 2, box.h - 2); ctx.clip();
      function poly(ring, fill, stroke, lw) {
        ctx.beginPath(); ring.forEach(function (p, i) { if (i) ctx.lineTo(X(p), Y(p)); else ctx.moveTo(X(p), Y(p)); }); ctx.closePath();
        if (fill) { ctx.fillStyle = fill; ctx.fill(); } ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke();
      }
      function centre(ring) { var sx = 0, sy = 0; ring.forEach(function (p) { sx += p[0]; sy += p[1]; }); return [sx / ring.length, sy / ring.length]; }
      sh.neighbours.forEach(function (n) {
        poly(n.ring, n.estimated ? '#f1f5f9' : '#ffffff', '#334155', 2);
        var c = centre(n.ring);
        if (n.label && k * 8 > 14) { ctx.fillStyle = '#334155'; ctx.font = Math.min(34, Math.max(18, k * 3.2)) + 'px ' + FONT; ctx.textAlign = 'center'; ctx.fillText(fa(n.label), X(c), Y(c)); }
      });
      poly(sh.plot, '#fde047', '#111827', 4);
      var pc = centre(sh.plot);
      ctx.fillStyle = '#111827'; ctx.font = 'bold ' + Math.min(52, Math.max(26, k * 4.2)) + 'px ' + FONT; ctx.textAlign = 'center';
      ctx.fillText(fa(data.plot_label || ''), X(pc), Y(pc) - 14);
      ctx.font = Math.min(30, Math.max(18, k * 2.4)) + 'px ' + FONT; ctx.fillText(fa(sh.area) + ' م²', X(pc), Y(pc) + 28);
      // edge lengths, placed outside the plot
      sh.edges.forEach(function (e) {
        var mx = (e.a[0] + e.b[0]) / 2, my = (e.a[1] + e.b[1]) / 2, dx = e.b[0] - e.a[0], dy = e.b[1] - e.a[1], len = Math.hypot(dx, dy) || 1;
        var nx = dy / len, ny = -dx / len;
        if ((mx - pc[0]) * nx + (my - pc[1]) * ny < 0) { nx = -nx; ny = -ny; }
        var tx = X([mx, my]) + nx * 34, ty = Y([mx, my]) - ny * 34;
        ctx.font = 'bold 26px ' + FONT; var label = fa(e.length.toFixed(2)), w = ctx.measureText(label).width + 12;
        ctx.fillStyle = 'rgba(255,255,255,.88)'; ctx.fillRect(tx - w / 2, ty - 15, w, 30);
        ctx.fillStyle = '#b91c1c'; ctx.fillText(label, tx, ty);
      });
      ctx.restore();
      // north arrow and a 10 m bar
      ctx.strokeStyle = INK; ctx.fillStyle = INK; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(box.x + 70, box.y + 110); ctx.lineTo(box.x + 70, box.y + 36); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(box.x + 70, box.y + 22); ctx.lineTo(box.x + 58, box.y + 50); ctx.lineTo(box.x + 82, box.y + 50); ctx.closePath(); ctx.fill();
      ctx.font = 'bold 26px ' + FONT; ctx.textAlign = 'center'; ctx.fillText('شمال', box.x + 70, box.y + 134);
      ctx.beginPath(); ctx.moveTo(box.x + box.w - 60 - 10 * k, box.y + box.h - 40); ctx.lineTo(box.x + box.w - 60, box.y + box.h - 40); ctx.lineWidth = 6; ctx.stroke();
      ctx.font = '24px ' + FONT; ctx.fillText(fa('۱۰ متر'), box.x + box.w - 60 - 5 * k, box.y + box.h - 66);
    }
    ctx.fillStyle = INK; ctx.textAlign = 'right'; ctx.font = '32px ' + FONT;
    var lines = [
      'مالک: ' + (f1.name || '') + (f1.father ? ' فرزند ' + f1.father : ''),
      'روستای ' + (f1.village || '') + '، بخش ' + (f1.district || '') + '، شهرستان ' + (f1.county || ''),
      'مساحت: ' + (f1.area || '') + ' مترمربع' + (data.renewal_code ? '    کد نوسازی: ' + data.renewal_code : ''),
      'شمالاً: ' + limitText('north') + '    جنوباً: ' + limitText('south'),
      'غرباً: ' + limitText('west') + '    شرقاً: ' + limitText('east')
    ];
    lines.forEach(function (t, i) { ctx.fillText(fa(t), W - 100, 1560 + i * 52); });
    ctx.font = '24px ' + FONT; ctx.fillStyle = '#64748b'; ctx.textAlign = 'center';
    ctx.fillText('این نقشه از پایگاه نقشه‌ی دهیاری تهیه شده است؛ طول‌ها به متر و بدون مقیاس رسمی‌اند.', W / 2, 1865);
    ctx.fillStyle = INK; ctx.font = 'bold 30px ' + FONT; ctx.textAlign = 'left'; ctx.fillText('مهر و امضای دهیاری', 110, 1790);
    if (!data.form1_saved) stamp('پیش‌نویس');
  }
  function limitText(side) { var l = (f1.limits || {})[side] || {}; return (Number(num(l.length)) ? l.length + ' متر ' : '') + (l.to || ''); }

  var DRAW = { f1: drawForm1, f2: drawForm2, sheet: drawSheet };
  function draw(which) { page = which || page; ctx.clearRect(0, 0, W, H); DRAW[page](); }
  function pageCanvas(which) { var keep = page; draw(which); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  // ---------- live preview ----------
  function readForm(form, target, prefix) {
    form.querySelectorAll('[data-' + prefix + ']').forEach(function (el) {
      var key = el.getAttribute('data-' + prefix);
      target[key] = el.type === 'checkbox' ? el.checked : el.value;
    });
  }
  function readLimits() {
    f1.limits = f1.limits || {};
    document.querySelectorAll('[data-limit]').forEach(function (el) {
      var parts = el.getAttribute('data-limit').split('.');
      f1.limits[parts[0]] = f1.limits[parts[0]] || {}; f1.limits[parts[0]][parts[1]] = el.value;
    });
  }
  function refresh() { readForm(document.getElementById('pff-f1'), f1, 'f1'); readLimits(); readForm(document.getElementById('pff-f2'), f2, 'f2'); draw(); }
  document.querySelectorAll('.pff-form').forEach(function (form) {
    form.addEventListener('input', refresh); form.addEventListener('change', refresh);
    form.addEventListener('focusin', function (e) { var w = form.getAttribute('data-form'); if (w !== page && page !== 'sheet') { setTab(w); } });
  });
  function setTab(which) {
    document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-page') === which); });
    draw(which);
  }
  document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.addEventListener('click', function () { setTab(b.getAttribute('data-page')); }); });

  // ---------- a minimal PDF: one JPEG per page ----------
  function toJpeg(c) {
    return new Promise(function (resolve) { c.toBlob(function (blob) { blob.arrayBuffer().then(function (buf) { resolve(new Uint8Array(buf)); }); }, 'image/jpeg', 0.92); });
  }
  function makePdf(pages) {
    var enc = new TextEncoder(), chunks = [], offsets = [], size = 0, pw = 595.28, ph = 841.89;
    function add(x) { var b = typeof x === 'string' ? enc.encode(x) : x; chunks.push(b); size += b.length; }
    function begin(n) { offsets[n] = size; add(n + ' 0 obj\n'); }
    var n = pages.length, kids = [];
    for (var i = 0; i < n; i++) kids.push((3 + i * 3) + ' 0 R');
    add('%PDF-1.4\n%\xE2\xE3\xCF\xD3\n');
    begin(1); add('<< /Type /Catalog /Pages 2 0 R >>\nendobj\n');
    begin(2); add('<< /Type /Pages /Kids [' + kids.join(' ') + '] /Count ' + n + ' >>\nendobj\n');
    pages.forEach(function (jpg, i) {
      var pageNo = 3 + i * 3, contentNo = pageNo + 1, imageNo = pageNo + 2;
      var h = ph, w = h * W / H; if (w > pw) { w = pw; h = w * H / W; }
      var x = (pw - w) / 2, y = (ph - h) / 2;
      begin(pageNo); add('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + pw + ' ' + ph + '] /Resources << /XObject << /Im0 ' + imageNo + ' 0 R >> >> /Contents ' + contentNo + ' 0 R >>\nendobj\n');
      var content = 'q ' + w.toFixed(2) + ' 0 0 ' + h.toFixed(2) + ' ' + x.toFixed(2) + ' ' + y.toFixed(2) + ' cm /Im0 Do Q';
      begin(contentNo); add('<< /Length ' + content.length + ' >>\nstream\n' + content + '\nendstream\nendobj\n');
      begin(imageNo); add('<< /Type /XObject /Subtype /Image /Width ' + W + ' /Height ' + H + ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ' + jpg.length + ' >>\nstream\n');
      add(jpg); add('\nendstream\nendobj\n');
    });
    var xref = size, total = 3 + n * 3;
    add('xref\n0 ' + total + '\n0000000000 65535 f \n');
    for (var k = 1; k < total; k++) add(String(offsets[k]).padStart(10, '0') + ' 00000 n \n');
    add('trailer\n<< /Size ' + total + ' /Root 1 0 R >>\nstartxref\n' + xref + '\n%%EOF');
    return new Blob(chunks, { type: 'application/pdf' });
  }
  function save(blob, name) {
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  }
  async function download(which, name) {
    var jpgs = [];
    for (var i = 0; i < which.length; i++) jpgs.push(await toJpeg(pageCanvas(which[i])));
    save(makePdf(jpgs), name);
  }
  document.getElementById('pff-dl1').addEventListener('click', function () { download(['f1', 'sheet'], 'form1-permit-' + data.file + '.pdf'); });
  document.getElementById('pff-dl2').addEventListener('click', function () { download(['f2'], 'form2-permit-' + data.file + '.pdf'); });
  document.getElementById('pff-print').addEventListener('click', async function () {
    var win = window.open('', '_blank');
    var urls = [];
    for (var w of ['f1', 'sheet', 'f2']) urls.push(pageCanvas(w).toDataURL('image/jpeg', 0.92));
    var doc = win.document, style = doc.createElement('style');
    doc.title = 'چاپ فرم‌ها';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}';
    doc.head.appendChild(style);
    urls.forEach(function (u) { var im = doc.createElement('img'); im.src = u; doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  // ---------- start ----------
  function load(src) { return new Promise(function (resolve, reject) { var im = new Image(); im.onload = function () { resolve(im); }; im.onerror = reject; im.src = src; }); }
  Promise.all([load(data.blank.form1), load(data.blank.form2), document.fonts.load('30px Vazirmatn'), document.fonts.load('bold 30px Vazirmatn')]).then(function (r) {
    images.f1 = r[0]; images.f2 = r[1];
    document.getElementById('pff-loading').hidden = true;
    refresh();
  });
})();
