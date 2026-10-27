/* Permit file, services: the letters the dehyari gives the owner for electricity, gas and water, typeset on the dehyari's letterhead
   from the file's data (json_script #pfv-data) and the inputs on the page; downloaded as PDF or printed, signed and stamped by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfv-data').textContent), F = data.f;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, XR = 1245, XL = 150, INK = '#0a1f6e', BLACK = '#111827', FONT = 'Vazirmatn, Tahoma, sans-serif', letterhead = null, page = 1;
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }

  function txt(s, x, y, size, color, align, bold) {
    s = fa(s); if (!s) return;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = align || 'right'; ctx.fillStyle = color || BLACK;
    ctx.font = (bold ? 'bold ' : '') + size + 'px ' + FONT; ctx.fillText(s, x, y); ctx.restore();
  }
  // a template with {key} holes -> the words laid right to left, the values inked
  function paragraph(template, x1, x0, y, lineH, size) {
    var parts = String(template).split(/(\{\w+\})/).filter(function (p) { return p !== ''; }), words = [];
    parts.forEach(function (p) {
      var m = /^\{(\w+)\}$/.exec(p);
      if (m) { var v = fa(F[m[1]] || ''); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); else words.push({ text: '.'.repeat(8), dots: true }); }
      else p.split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
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
  function paragraphs(list, y, lineH, size) {
    list.forEach(function (t) { y = paragraph(t, XR, XL, y, lineH, size) + lineH + 24; });
    return y;
  }

  var BODY = {
    elec_permit: ['به پیوست درخواست و پروانه شماره {permit_no} مورخ {permit_date} آقای {name} فرزند {father} به شماره ملی {national_id} جهت واگذاری یک انشعاب برق برای منزل واقع در طرح هادی روستای {village} - {address} - پلاک {plot} - کد پستی {postal_code} ارسال می‌گردد. لذا واگذاری انشعاب برق از نظر این دهیاری بلامانع می‌باشد.'],
    elec_endwork: ['به پیوست تصویر نامه آقای {name} فرزند {father} دارای کد ملی {national_id} مبنی بر درخواست واگذاری یک انشعاب برق برای منزل واقع در طرح هادی روستای {village} - {address} - پلاک {plot} با توجه به پایان‌کار شماره {endwork_no} مورخ {endwork_date} ارسال می‌گردد؛ لذا واگذاری انشعاب برق از نظر این دهیاری بلامانع می‌باشد.'],
    gas_meter: ['به پیوست درخواست آقای {name} فرزند {father} جهت جانمایی و نصب علمک گاز برای منزل واقع در طرح هادی روستای {village} - {address} - پلاک {plot} - کد پستی {postal_code} (کروکی پیوست) ارسال می‌گردد. خواهشمند است در صورت امکان دستور به مساعدت فرمایید.'],
    gas_dig: ['احتراماً عطف به نامه شماره {ref_no} مورخ {ref_date} به اطلاع می‌رساند آقای {name} فرزند {father} هزینه آسفالت شکافی را طی فیش بانکی شماره {slip_no} مورخ {slip_date} پرداخت نموده و حفاری از نظر این دهیاری بلامانع است.',
              'لازم به ذکر است اخذ استعلام از سایر دستگاه‌ها و رعایت اصول ایمنی و استانداردها در تمامی مراحل کار الزامی می‌باشد.',
              'ضمناً در صورتی که محاسبه متراژ آن اداره محترم درخصوص آسفالت شکافی اشتباه باشد هیچ‌گونه وجهی استرداد داده نخواهد شد.'],
    water_permit: ['به پیوست درخواست و پروانه شماره {permit_no} مورخ {permit_date} آقای {name} فرزند {father} جهت واگذاری یک انشعاب آب برای منزل مسکونی نوساز واقع در طرح هادی روستای {village} - {address} ارسال می‌گردد. لذا واگذاری انشعاب آب از نظر این دهیاری بلامانع می‌باشد.',
                   'ضمناً متراژ آسفالت شکافی به دهیاری اعلام گردد.']
  };
  var STATUS = ['طبق بررسی‌های انجام شده و به استناد بند ۱۱ ماده ۶۹ قانون تشکیلات، وظایف، و انتخابات شورای اسلامی کشور و ماده ۳ قانون تعاریف محدوده و حریم شهر و روستا ملک فوق با کاربری مسکونی به مساحت عرصه {area} مترمربع و اعیان {built} مترمربع به حدود اربعه: شمال: {n} جنوب: {s} شرق: {e} غرب: {w} در داخل طرح هادی روستا منطبق با طرح هادی مصوب ابلاغی {hadi_date} و {basis} عرض معبر {street} متر می‌باشد.',
                'لذا واگذاری یک انشعاب {what} به آقای {name} به شماره ملی {national_id} از نظر این دهیاری با مختصات جغرافیایی x: {utm_x} y: {utm_y} بلامانع می‌باشد.',
                'توضیحات: {notes}'];

  function head() {
    ctx.clearRect(0, 0, W, H); ctx.drawImage(letterhead, 0, 0, W, H);
    txt(F.number, 300, 143, 30, INK, 'right'); txt(F.date, 300, 190, 30, INK, 'right');
  }
  function signature(y) {
    ctx.save(); ctx.fillStyle = BLACK; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.direction = 'rtl'; ctx.font = 'bold 32px ' + FONT;
    ctx.fillText('با تشکر', 430, y); ctx.fillText(fa(F.dehyari_name || ''), 430, y + 55); ctx.fillText(fa('دهیار ' + (F.village || '')), 430, y + 110); ctx.fillText('مهر و امضاء', 430, y + 175); ctx.restore();
  }
  // the non-violation certificate (گواهی عدم خلاف): title, village / section, one paragraph, the two signatures
  function certificate() {
    head();
    txt('گواهی عدم خلاف', 700, 470, 56, BLACK, 'center', true);
    txt('روستای: ' + (F.village || ''), XR, 560, 31, BLACK, 'right', true); txt('بخش: ' + (F.section || ''), 560, 560, 31, BLACK, 'right', true);
    var y = paragraph('با توجه به پیرو پروانه ساختمانی شماره {permit_no} مورخ {permit_date} مربوط به پلاک ثبتی شماره {plot} در پاسخ به درخواست شماره {req_no} مورخ {req_date} خانم/آقای {name} و به نشانی {address} بر حسب گزارش مورخ {report_date} ناظر فنی {sup_name} اعلام می‌دارد که ساختمان احداث شده در مرحله {stage_text} می‌باشد و ادامه عملیات ساختمانی آن بلامانع است.', XR, XL, 650, 68, 31);
    txt('ملاحظات:', XR, y + 110, 30, BLACK, 'right', true);
    paragraph('{notes}', XR, XL, y + 170, 60, 29);
    ctx.save(); ctx.fillStyle = BLACK; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.direction = 'rtl'; ctx.font = 'bold 30px ' + FONT;
    ctx.fillText('نام و امضاء مسئول فنی دهیاری', 960, 1500); ctx.fillText('نام و امضاء دهیار', 400, 1500);
    ctx.fillStyle = INK; ctx.font = '30px ' + FONT; ctx.fillText(fa(F.tech_name || ''), 960, 1445); ctx.fillText(fa(F.dehyari_name || ''), 400, 1445); ctx.restore();
  }
  function letter() {
    if (/^nov_/.test(data.kind)) { certificate(); return; }
    head();
    txt(data.company, XR, 470, 34, BLACK, 'right', true);
    txt('با سلام و احترام؛', XR, 540, 31, BLACK, 'right', true);
    var list = BODY[data.kind] || STATUS;
    F.what = data.what;
    var y = paragraphs(list, 625, 66, 31);
    signature(Math.max(y + 40, 1050));
  }
  function request() {
    head();
    ctx.save(); ctx.fillStyle = '#16a34a'; ctx.beginPath(); ctx.roundRect(155, 62, 160, 44, 10); ctx.fill(); ctx.restore(); txt('فرم شماره ۲', 235, 86, 28, '#fff', 'center', true);
    txt('شورای اسلامی / دهیاری محترم روستای ' + (F.village || ''), XR, 450, 34, BLACK, 'right', true);
    var y = paragraph('به استناد ماده ۸ قانون منع فروش و واگذاری اراضی فاقد کاربری مسکونی برای اسکان به شرکت‌های تعاونی مسکونی و سایر اشخاص حقیقی و حقوقی و ماده ۱۵ آیین‌نامه استفاده از اراضی احداث بنا و تاسیسات در داخل طرح هادی روستا و یا خارج از حریم شهرها و محدوده روستاها.', XR, XL, 530, 58, 27);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(150, y + 60, 1100, 780, 60); ctx.stroke(); ctx.restore();
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(190, y + 100, 330, 330, 40); ctx.stroke(); ctx.restore();
    txt('کروکی ملک', 355, y + 140, 28, BLACK, 'center', true);
    txt('(نقشه‌ی ملک را چاپ و اینجا بچسبانید)', 355, y + 270, 20, '#9ca3af', 'center');
    var yy = y + 130, lines = ['آقا/خانم: {name}    فرزند: {father}', 'شماره شناسنامه: {id_number}    صادره از: {issued_at}', 'جهت: واحد مسکونی به آدرس: شهرستان: بیرجند',
      'بخش: {section}    روستای: {village}    {address}', 'پلاک: {plot}    کدپستی: {postal_code}', 'تلفن همراه: {phone}'];
    lines.forEach(function (t) { paragraph(t, XR - 40, 560, yy, 50, 28); yy += 74; });
    paragraph('درخواست انشعاب {what} دارد. خواهشمند است درخصوص وضعیت ملک نامبرده اعلام نظر فرمایید.', XR - 40, 560, yy + 10, 56, 28);
    txt(data.company.replace('مدیر محترم', 'مدیر'), XR - 40, y + 760, 28, BLACK, 'right', true);
  }
  function draw(n) { page = n || page; F.what = data.what; if (page === 2 && data.pages === 2) request(); else letter(); }
  function pageCanvas(n) { var keep = page; draw(n); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  var form = document.getElementById('pfv-form');
  function read() { form.querySelectorAll('input[name^="f_"]').forEach(function (el) { F[el.name.slice(2)] = el.value; }); }
  form.addEventListener('input', function () { read(); draw(); });
  document.querySelectorAll('.pfs-tabs button').forEach(function (b) { b.addEventListener('click', function () {
    document.querySelectorAll('.pfs-tabs button').forEach(function (x) { x.classList.toggle('is-on', x === b); }); draw(parseInt(b.getAttribute('data-page'), 10)); }); });
  function pagesList() { return data.pages === 2 ? [1, 2] : [1]; }
  document.getElementById('pfv-dl').addEventListener('click', async function () {
    var jpgs = []; for (var i of pagesList()) jpgs.push(await PdfLite.toJpeg(pageCanvas(i)));
    PdfLite.save(PdfLite.make(jpgs, W, H), 'service-letter-' + data.kind + '-' + data.file + '.pdf');
  });
  document.getElementById('pfv-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'); doc.title = 'چاپ نامه';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}'; doc.head.appendChild(style);
    pagesList().forEach(function (n) { var im = doc.createElement('img'); im.src = pageCanvas(n).toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });
  var img = new Image();
  img.onload = function () {
    letterhead = img;
    document.fonts.load('30px Vazirmatn').then(function () { return document.fonts.load('bold 30px Vazirmatn'); }).then(function () { document.getElementById('pff-loading').hidden = true; read(); draw(); });
  };
  img.src = data.letterhead;
})();
