/* Construction without a permit, step 2: the request form («فرم درخواست») and the undertaking («تعهدنامه») for the Article 99
   commission file, typeset in the browser from the file's data (json_script #pcm-data) on a plain bordered page like the village's
   own forms, then downloaded as PDF or printed. The owner signs and leaves a fingerprint by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pcm-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREY = '#6b7280', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var R = 1235, L = 165;                       // right and left text margins inside the frame
  var page = 'request';
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }

  function frame() {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = BLACK; ctx.lineWidth = 12; ctx.strokeRect(70, 50, W - 140, H - 100);
    ctx.lineWidth = 3; ctx.strokeRect(94, 74, W - 188, H - 148);
  }
  function text(t, x, y, size, opts) {
    opts = opts || {};
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = opts.align || 'right';
    ctx.fillStyle = opts.color || BLACK; ctx.font = (opts.bold ? 'bold ' : '') + size + 'px ' + FONT;
    ctx.fillText(t, x, y);
  }
  // parts: [{t: fixed text} | {v: value, w: width of the dotted blank when empty}] in reading order (right to left)
  function paragraph(parts, y, lineH, size) {
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(p.w || 18), ink: false, dots: true }); }
    });
    var space = size * 0.3, x = R, line = y;
    words.forEach(function (w) {
      ctx.font = (w.ink ? 'bold ' : '') + size + 'px ' + FONT;
      var width = ctx.measureText(w.text).width;
      if (x - width < L) { x = R; line += lineH; }
      ctx.fillStyle = w.ink ? INK : (w.dots ? GREY : BLACK);
      ctx.fillText(w.text, x, line);
      x -= width + space;
    });
    return line;
  }
  function tick(cx, cy) {
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 4; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(cx - 9, cy + 1); ctx.lineTo(cx - 3, cy + 8); ctx.lineTo(cx + 10, cy - 9); ctx.stroke(); ctx.restore();
  }
  function signBox(label, x, y) { text(label, x, y, 32, { bold: true }); }

  function drawRequest() {
    var f = data.form;
    frame();
    text('بسمه تعالی', W / 2, 140, 42, { bold: true, align: 'center' });
    text('«فرم درخواست»', R, 270, 54, { bold: true });
    text('تاریخ: ' + fa(f.date), 400, 270, 36, { color: INK, bold: true, align: 'left' });
    text((f.addressee === 'dehyari' ? 'دهیار روستای ' : 'شورای اسلامی روستای ') + fa(data.village), R, 430, 46, { bold: true });
    text('باسلام', R, 520, 36);
    var y = paragraph([{ t: 'اینجانب' }, { v: f.name, w: 26 }, { t: 'فرزند' }, { v: f.father, w: 20 }, { t: 'باشماره شناسنامه' }, { v: f.id_number, w: 14 },
      { t: 'ساکن روستای' }, { v: data.village, w: 12 }, { t: '، خیابان' }, { v: f.street, w: 40 }], 610, 82, 35);
    y = paragraph([{ t: 'تقاضای' }, { v: f.subject, w: 40 }, { t: 'را دارم. خواهشمند است در صورت امکان مساعدت فرمایید.' }], y + 110, 82, 35);
    y = paragraph([{ t: 'تلفن تماس:' }, { v: f.phone, w: 28 }], y + 100, 82, 35);
    signBox('امضاء واثرانگشت متقاضی', R, y + 130);
    paragraph([{ t: 'ضمنا شماره تماس اعلامی متعلق به اینجانب می باشد که دهیاری از طریق آن هزینه های دهیاری ، جریمه و هرگونه پیام اطلاع رسانی را به اینجانب ابلاغ خواهد نمود.' }], y + 480, 82, 35);
  }

  var ITEMS = [
    'عدم هدایت فاضلاب و شستشوی حیاط به معبر',
    'پرهیز از غذا دادن در معابر به حیوانات پرسه زن (سگ و گربه)',
    'پیاده رو سازی',
    'نما سازی',
    'تامین پارکینگ',
    'اخذ رضایت همسایگان مجاور در صورت نیاز (ضمنا مسئولیت صحت مندرجات داخل پرونده و امضا های اخذ شده توسط اینجانب را بعهده میگیرم)',
    'در صورتیکه در زمان اخذ هزینه ها جهت صدور هر گونه پاسخ قسمتی از ردیف های درآمدی که مشمول ملک مورد نظر می گردیده و از قلم افتاده است، دهیاری میبایست بر اساس نرخ زمان پاسخ نسبت به برآورد هزینه مذکور در زمان مراجعه شهروند اقدام به وصول نماید.',
    'در صورتیکه ۲۴ ساعت پس از دریافت خدمات (آب و برق) مصالح از داخل معبر و جوی جمع آوری نشود دهیاری مجاز است بدون اخطار قبلی مصالح را جمع آوری نماید و اینجانب حق هیچگونه اعتراضی ندارم.',
    'چنانچه اشخاص حقیقی و حقوقی از معابر یا فضای عمومی تا یک سوم عرض معبر در هنگام ساخت و ساز اشغال کنند ماهیانه ................ ریال برای هر متر مربع سطح اشغال اخذ شود.',
    'کلیه مسئولیت های ایمنی استفاده از معابر جهت انباشت مصالح ، تجهیزات و .. بر عهده مالک بوده و ملزم به رعایت نکات ایمنی می باشد.'
  ];
  function drawUndertaking() {
    var f = data.form;
    frame();
    text('« تعهد نامه »', W / 2, 140, 42, { bold: true, align: 'center' });
    var y = paragraph([{ t: 'اینجانب' }, { v: f.name, w: 24 }, { t: 'فرزند' }, { v: f.father, w: 18 }, { t: 'باشماره ملی' }, { v: f.national_id, w: 14 },
      { t: 'ساکن روستای' }, { v: data.village, w: 12 }, { t: '، خیابان' }, { v: f.street, w: 36 }], 240, 72, 33);
    y = paragraph([{ t: 'متعهد و مکلف میگردم نسبت به اجرای موارد ذیل اقدام نموده و در صورت تخلف و معرفی به بهداشت و مراجع قضایی، پذیرا بوده و حق هرگونه اعتراضی را از خود ساقط نمایم.' }], y + 100, 72, 33);
    y += 90;
    ITEMS.forEach(function (item) {
      tick(R + 6, y);
      R -= 34; y = paragraph([{ t: item }], y, 58, 32); R += 34;
      y += 74;
    });
    signBox('امضاء واثرانگشت متقاضی', R, Math.min(y + 50, 1850));
  }

  var DRAW = { request: drawRequest, undertaking: drawUndertaking };
  var NAMES = { request: 'form-request', undertaking: 'form-undertaking' };
  function draw(which) { page = which || page; ctx.clearRect(0, 0, W, H); DRAW[page](); }
  function pageCanvas(which) { var keep = page; draw(which); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  function readInputs() {
    document.querySelectorAll('#pcm-form input[name], #pcm-form select[name]').forEach(function (el) { if (el.name in data.form) data.form[el.name] = el.value; });
  }
  function refresh() { readInputs(); draw(); }
  var form = document.getElementById('pcm-form');
  if (form) { form.addEventListener('input', refresh); form.addEventListener('change', refresh); }
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
  document.getElementById('pcm-dl-this').addEventListener('click', function () { download([page], NAMES[page] + '-' + data.file + '.pdf'); });
  document.getElementById('pcm-dl-all').addEventListener('click', function () { download(['request', 'undertaking'], 'commission-forms-' + data.file + '.pdf'); });
  document.getElementById('pcm-print').addEventListener('click', function () {
    var win = window.open('', '_blank'), urls = [];
    ['request', 'undertaking'].forEach(function (w) { urls.push(pageCanvas(w).toDataURL('image/jpeg', 0.92)); });
    var doc = win.document, style = doc.createElement('style');
    doc.title = 'چاپ فرم‌ها';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}';
    doc.head.appendChild(style);
    urls.forEach(function (u) { var im = doc.createElement('img'); im.src = u; doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  Promise.all([document.fonts.load('30px Vazirmatn'), document.fonts.load('bold 30px Vazirmatn')]).then(function () {
    document.getElementById('pff-loading').hidden = true;
    refresh();
  });
})();
