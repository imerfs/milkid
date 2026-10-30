/* Construction without a permit, step 5: the dehyari's letter introducing the owner to a judiciary expert (on the dehyari's letterhead),
   the neighbours' consent form and the draft of the notarial undertaking. Typeset in the browser from the file's data (json_script
   #pcm-data); the preview follows the forms on the page; downloaded as PDF or printed. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pcm-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', BLACK = '#111827', GREY = '#6b7280', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var R = 1245, L = 150, FA = '۰۱۲۳۴۵۶۷۸۹', letterhead = null, page = 'letter', deedPage = 0;
  var SIDE = {}; data.sides.forEach(function (s) { SIDE[s[0]] = s[1]; });
  function fa(t) { return String(t == null ? '' : t).replace(/(\d)\.(?=\d)/g, '$1٫').replace(/\d/g, function (d) { return FA[d]; }); }

  function text(t, x, y, size, o) {
    o = o || {};
    ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = o.align || 'right';
    ctx.fillStyle = o.color || BLACK; ctx.font = (o.bold ? 'bold ' : '') + size + 'px ' + FONT;
    ctx.fillText(t, x, y);
  }
  // words laid out right to left, wrapped between x1 (right) and x0 (left); values in ink, empty values as dots
  function words(parts) {
    var out = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) out.push({ text: w }); });
      else { var s = fa(p.v); if (s) s.split(' ').forEach(function (w) { out.push({ text: w, ink: true }); }); else out.push({ text: '.'.repeat(p.w || 14), dots: true }); }
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
  function frame() { ctx.strokeStyle = BLACK; ctx.lineWidth = 6; ctx.strokeRect(50, 40, W - 100, H - 80); }
  function line(x0, x1, y) { ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); }

  // ---------- the introduction letter ----------
  function drawLetter() {
    var l = data.letter;
    ctx.clearRect(0, 0, W, H); if (letterhead) ctx.drawImage(letterhead, 0, 0, W, H); else { ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H); }
    text(fa(l.number), 300, 143, 30, { color: INK, bold: true }); text(fa(l.date), 300, 190, 30, { color: INK, bold: true });      // the letterhead prints the labels
    text('جناب آقای مهندس ' + fa(l.expert || '…………………'), R, 520, 38, { bold: true });
    text('سلام علیکم', R, 610, 32);
    var y = paragraph([
      { t: 'با احترام؛ با عنایت به تصمیم اعضاء محترم کمیسیون ماده ۹۹ قانون دهیاریها مقتضی است از ملک آقای/خانم' }, { v: l.owner, w: 18 },
      { t: 'به آدرس' }, { v: l.address, w: 24 }, { t: 'با شماره تماس' }, { v: l.phone, w: 12 },
      { t: 'بازدید بعمل آورده و نظریه کارشناسی ملک مذکور را اعلام فرمائید.' }], R, L, 720, 68, 33);
    text('باتشکر', 440, y + 150, 34, { bold: true, align: 'center' });
    text('دهیار ' + fa(l.village), 440, y + 210, 34, { bold: true, align: 'center' });
    if (l.signer) text(fa(l.signer), 440, y + 260, 28, { color: INK, bold: true, align: 'center' });
    text('مهر و امضاء', 440, y + 310, 26, { color: GREY, align: 'center' });
  }

  // ---------- the neighbours' consent ----------
  function drawConsent() {
    var c = data.consent, o = c.owner;
    blank(); frame();
    text('تعهدنامه مالک و همسایگان جهت تکمیل پرونده کمیسیون ماده ۹۹', W / 2, 110, 36, { bold: true, align: 'center' });
    var y = paragraph([
      { t: 'اینجانب' }, { v: o.name, w: 20 }, { t: 'فرزند' }, { v: o.father, w: 12 }, { t: 'با شماره ملی' }, { v: o.national_id, w: 12 }, { t: 'متولد' }, { v: o.birth, w: 10 },
      { t: 'ساکن روستای' }, { v: c.village, w: 10 }, { t: 'به آدرس' }, { v: o.address, w: 22 }, { t: 'با شماره تماس' }, { v: o.phone, w: 12 },
      { t: 'دارای یک باب منزل مسکونی می‌باشم. بدین‌وسیله اعلام می‌دارم با توجه به عدم رعایت سطح اشغال در ملک فوق‌الذکر، به منظور تکمیل پرونده در کمیسیون ماده ۹۹، رضایت همسایگان مجاور به شرح زیر اخذ گردیده است.' },
      { t: 'همچنین متعهد می‌گردم در صورتی که در آینده مشخص شود امضا یا اثر انگشت اخذشده متعلق به مالکین واقعی املاک مجاور نبوده است، مسئولیت کامل حقوقی و کیفری موضوع را شخصاً پذیرفته و دهیاری را از هرگونه مسئولیت یا تبعات قانونی در این خصوص مبرا می‌نمایم.' }],
      1320, 100, 190, 44, 25);
    text('با تشکر — امضاء و اثر انگشت مالک', 1320, y + 60, 24, { bold: true });
    line(100, 1320, y + 100);
    var top = y + 150;
    c.neighbours.forEach(function (n, i) {
      var yy = top + i * 440;
      text(fa(i + 1) + ' - اینجانب همسایه ضلع ' + (SIDE[n.side] || 'شرق / غرب / شمال / جنوب') + ' با مشخصات زیر', 1320, yy, 24, { bold: true });
      var e = paragraph([
        { t: 'نام و نام خانوادگی' }, { v: n.name, w: 22 }, { t: 'فرزند' }, { v: n.father, w: 12 }, { t: 'با شماره ملی' }, { v: n.national_id, w: 12 }, { t: 'متولد' }, { v: n.birth, w: 10 },
        { t: 'به نشانی محل سکونت' }, { v: n.address, w: 24 }, { t: 'با شماره تماس' }, { v: n.phone, w: 12 }], 1320, 100, yy + 50, 42, 24);
      e = paragraph([{ t: 'بدین‌وسیله ضمن اعلام رضایت کامل و بدون قید و شرط در خصوص پیشروی صورت‌گرفته در کلیه طبقات ملک آقای/خانم' }, { v: o.name, w: 12 },
        { t: 'گواهی می‌نمایم که مالکیت اینجانب بر ملک مجاور، واقعی، قانونی و مورد تأیید می‌باشد و اختیار قانونی لازم برای اعلام این رضایت را دارم. همچنین متعهد می‌گردم در صورت واگذاری یا انتقال ملک تحت مالکیت خود مراتب این رضایت و تعهد را به خریدار یا منتقل‌الیه اطلاع و تفهیم نمایم.' }], 1320, 100, e + 50, 40, 22);
      text('با تشکر — امضاء و اثر انگشت', 1320, e + 54, 22, { bold: true });
      line(100, 1320, yy + 420);
    });
  }

  // ---------- the notarial undertaking (a draft the notary finalises) ----------
  function deedLines() {
    var d = data.deed, size = 27, lineH = 50, x1 = 1320, x0 = 90, pages = [[]], first = true;
    var perFirst = 24, perOther = 33, count = 0;
    ctx.direction = 'rtl'; ctx.font = size + 'px ' + FONT;
    String(d.text || '').split('\n\n').forEach(function (par) {
      var row = [], x = x1;
      par.split(/\s+/).forEach(function (w) {
        var width = ctx.measureText(w).width;
        if (x - width < x0 && row.length) { push(row); row = []; x = x1; }
        row.push(w); x -= width + size * 0.3;
      });
      if (row.length) push(row);
      push(null);
    });
    function push(row) {
      var cap = pages.length === 1 ? perFirst : perOther;
      if (count >= cap) { pages.push([]); count = 0; }
      pages[pages.length - 1].push(row); count++;
    }
    return { pages: pages, size: size, lineH: lineH, x1: x1 };
  }
  function drawDeed(index) {
    var d = data.deed, lay = deedLines(), no = Math.min(index || 0, lay.pages.length - 1);
    blank(); frame();
    var y = 130;
    if (no === 0) {
      text('سند تعهدنامه غیرمالی', W / 2, 110, 40, { bold: true, align: 'center' });
      text('پیش‌نویس برای دفترخانه — متن نهایی را دفترخانه تنظیم می‌کند', W / 2, 165, 24, { color: GREY, align: 'center' });
      var yy = 230;
      [['نام متعهد:', d.owner], ['نام پدر:', d.father], ['شماره ملی:', d.national_id], ['شماره شناسنامه:', d.id_number], ['تاریخ تولد:', d.birth], ['شماره تلفن:', d.phone]].forEach(function (r, i) {
        var col = i % 3, row = Math.floor(i / 3), x = 1320 - col * 410, yv = yy + row * 70;
        ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.strokeRect(x - 400, yv - 30, 400, 60);
        text(r[0], x - 10, yv, 22, { bold: true }); text(fa(r[1]), x - 175, yv, 26, { color: INK, bold: true, max: 200 });
      });
      ctx.strokeRect(90, yy + 110, 1230, 60); text('نشانی:', 1310, yy + 140, 22, { bold: true }); text(fa(d.address), 1220, yy + 140, 26, { color: INK, bold: true });
      text('شرایط و متون حقوقی', W / 2, yy + 230, 28, { bold: true, align: 'center' }); line(90, 1320, yy + 255);
      y = yy + 300;
    }
    var yy2 = y;
    lay.pages[no].forEach(function (row) {
      if (row === null) { yy2 += lay.lineH * 0.5; return; }
      var x = lay.x1; ctx.font = lay.size + 'px ' + FONT; ctx.direction = 'rtl'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillStyle = BLACK;
      row.forEach(function (w) { ctx.fillText(w, x, yy2); x -= ctx.measureText(w).width + lay.size * 0.3; });
      yy2 += lay.lineH;
    });
    if (no === lay.pages.length - 1) {
      line(90, 1320, 1780); text('امضاء و اثر انگشت متعهد', 1300, 1830, 26, { bold: true });
    }
    text('صفحه ' + fa(no + 1) + ' از ' + fa(lay.pages.length), W / 2, 1930, 24, { color: GREY, align: 'center' });
    return lay.pages.length;
  }

  function draw() {
    if (page === 'letter') drawLetter(); else if (page === 'consent') drawConsent(); else buildDeedTabs(drawDeed(deedPage));
  }
  var tabs = document.getElementById('pcm-tabs');
  function buildDeedTabs(count) {
    tabs.querySelectorAll('.pcm-deed-page').forEach(function (b) { b.remove(); });
    if (count < 2) return;
    for (var i = 0; i < count; i++) {
      (function (idx) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'pcm-deed-page' + (idx === deedPage ? ' is-on' : ''); b.textContent = 'صفحه ' + fa(idx + 1);
        b.addEventListener('click', function () { deedPage = idx; draw(); }); tabs.appendChild(b);
      })(i);
    }
  }
  function setTab(which) {
    page = which; deedPage = 0;
    tabs.querySelectorAll('button[data-page]').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-page') === which); });
    if (which !== 'deed') tabs.querySelectorAll('.pcm-deed-page').forEach(function (b) { b.remove(); });
    draw();
  }
  tabs.querySelectorAll('button[data-page]').forEach(function (b) { b.addEventListener('click', function () { setTab(b.getAttribute('data-page')); }); });

  // ---------- the forms feed the preview ----------
  var consentForm = document.getElementById('pcm-consent-form'), deedForm = document.getElementById('pcm-deed-form'), letterForm = document.getElementById('pcm-letter-form');
  function read() {
    if (consentForm) {
      data.consent.neighbours.forEach(function (n, i) {
        ['side', 'name', 'father', 'national_id', 'birth', 'address', 'phone'].forEach(function (k) { var el = consentForm.elements['n' + i + '_' + k]; if (el) n[k] = el.value; });
      });
    }
    if (deedForm && deedForm.elements.text) data.deed.text = deedForm.elements.text.value;
    if (letterForm) {
      var pick = letterForm.elements.expert, found = data.letter.experts.filter(function (e) { return String(e.id) === String(pick.value); })[0];
      if (found) { data.letter.expert = found.name; data.letter.field = found.field; }
      data.letter.number = letterForm.elements.letter_no.value; data.letter.date = letterForm.elements.letter_date.value;
    }
    draw();
  }
  [consentForm, deedForm, letterForm].forEach(function (f) { if (f) { f.addEventListener('input', read); f.addEventListener('change', read); } });

  // ---------- output ----------
  var NAMES = { letter: 'expert-introduction', consent: 'neighbours-consent', deed: 'notarial-undertaking' };
  function pageCanvas() { var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); return c; }
  function allPages() {                      // the pages of the shown form (the deed has several)
    var out = [], keep = [page, deedPage];
    if (page === 'deed') { var n = deedLines().pages.length; for (var i = 0; i < n; i++) { deedPage = i; draw(); out.push(pageCanvas()); } }
    else out.push(pageCanvas());
    page = keep[0]; deedPage = keep[1]; draw();
    return out;
  }
  document.getElementById('pcm-dl').addEventListener('click', async function () {
    var jpgs = []; var canv = allPages(); for (var i = 0; i < canv.length; i++) jpgs.push(await PdfLite.toJpeg(canv[i]));
    PdfLite.save(PdfLite.make(jpgs, W, H), NAMES[page] + '-' + data.file + '.pdf');
  });
  document.getElementById('pcm-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style');
    doc.title = 'چاپ'; style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}';
    doc.head.appendChild(style);
    allPages().forEach(function (c) { var im = doc.createElement('img'); im.src = c.toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 500);
  });

  var img = new Image();
  img.onload = function () { letterhead = img; start(); };
  img.onerror = start;
  function start() {
    Promise.all([document.fonts.load('26px Vazirmatn'), document.fonts.load('bold 26px Vazirmatn')]).then(function () {
      document.getElementById('pff-loading').hidden = true; read();
    });
  }
  img.src = data.letterhead;
})();
