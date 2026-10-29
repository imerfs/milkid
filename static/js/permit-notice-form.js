/* Construction without a permit, step 3: the warning notice (اخطاریه به مالک, form 14) drawn over its blank form from the file's data
   (json_script #pnf-data); the staff change the values and the ticks, the preview follows; downloaded as PDF or printed. The dehyari
   stamps and signs and the owner signs in person. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pnf-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1414, H = 2000, INK = '#0a1f6e', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var FA = '۰۱۲۳۴۵۶۷۸۹', blank = null;
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }

  function put(text, x0, x1, y, align, size) {
    text = fa(text); if (!text) return;
    var s = size || 30;
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.fillStyle = INK; ctx.font = 'bold ' + s + 'px ' + FONT;
    while (ctx.measureText(text).width > (x1 - x0) && s > 14) { s -= 1; ctx.font = 'bold ' + s + 'px ' + FONT; }
    ctx.textAlign = align === 'right' ? 'right' : 'center';
    ctx.fillText(text, align === 'right' ? x1 - 4 : (x0 + x1) / 2, y);
  }
  function dot(x, y, r) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = INK; ctx.fill(); }

  // the centres of the circles on the blank form
  var TICK = { rules: [641, 768], permit: [426, 768], plans: [1134, 827], technical: [921, 827], extra: [619, 825] };
  var POSITION = { inside: [1059, 1089], outside: [718, 1081] };
  var DELIVERY = { handed: [257, 1536], posted: [363, 1637] };

  function draw() {
    var f = data.form;
    ctx.clearRect(0, 0, W, H); ctx.drawImage(blank, 0, 0, W, H);
    put(f.number, 240, 450, 250, 'right'); put(f.date, 240, 488, 294, 'right');
    put(f.addressee, 822, 1056, 706, 'center', 32);
    Object.keys(TICK).forEach(function (k) { if (f.ticks && f.ticks[k]) dot(TICK[k][0], TICK[k][1], 13); });
    if (POSITION[f.position]) dot(POSITION[f.position][0], POSITION[f.position][1], 14);
    if (DELIVERY[f.delivery]) dot(DELIVERY[f.delivery][0], DELIVERY[f.delivery][1], 14);
    put(f.address, 300, 1075, 1222, 'right', 32);
  }

  var form = document.getElementById('pnf-form');
  function read() {
    if (form) {
      form.querySelectorAll('[name]').forEach(function (el) {
        var n = el.name, m;
        if ((m = /^tick_(\w+)$/.exec(n))) data.form.ticks[m[1]] = el.checked;
        else if (n in data.form && n !== 'ticks') data.form[n] = el.value;
      });
    }
    draw();
  }
  if (form) { form.addEventListener('input', read); form.addEventListener('change', read); }

  function pageCanvas() { var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); return c; }
  document.getElementById('pnf-dl').addEventListener('click', async function () {
    PdfLite.save(PdfLite.make([await PdfLite.toJpeg(pageCanvas())], W, H), 'warning-notice-' + data.file + '.pdf');
  });
  document.getElementById('pnf-print').addEventListener('click', function () {
    var win = window.open('', '_blank'), doc = win.document, style = doc.createElement('style'), im = doc.createElement('img');
    doc.title = 'چاپ اخطاریه';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}';
    doc.head.appendChild(style); im.src = pageCanvas().toDataURL('image/jpeg', 0.92); doc.body.appendChild(im);
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  var img = new Image();
  img.onload = function () {
    blank = img;
    document.fonts.load('bold 30px Vazirmatn').then(function () { document.getElementById('pff-loading').hidden = true; read(); });
  };
  img.src = data.blank;
})();
