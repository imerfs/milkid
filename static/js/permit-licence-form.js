/* Permit file, step 7: the building permit form (three pages) drawn in the browser from the file's data (json_script #pfl-data) and
   the inputs on the page, downloaded as PDF or printed. The dehyari and the supervising engineer sign and stamp it by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfl-data').textContent), F = data.f, CH = data.choices;
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, XR = 1310, XL = 90, INK = '#0a1f6e', BLACK = '#111827', FONT = 'Vazirmatn, Tahoma, sans-serif';
  var page = 1, letterhead = null;
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }
  function val(k) { return F[k] == null ? '' : F[k]; }

  function txt(s, x, y, size, color, align, bold) {
    s = fa(s); if (!s) return 0;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = align || 'right'; ctx.fillStyle = color || BLACK;
    ctx.font = (bold ? 'bold ' : '') + size + 'px ' + FONT; var w = ctx.measureText(s).width; ctx.fillText(s, x, y); ctx.restore(); return w;
  }
  function width(s, size, bold) { ctx.save(); ctx.font = (bold ? 'bold ' : '') + size + 'px ' + FONT; var w = ctx.measureText(fa(s)).width; ctx.restore(); return w; }
  function dots(x0, x1, y) { ctx.save(); ctx.strokeStyle = '#9ca3af'; ctx.setLineDash([2, 5]); ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); ctx.restore(); }
  function box(y0, y1) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(XL, y0, XR - XL, y1 - y0, 22); ctx.stroke(); ctx.restore(); }
  function fit(s, maxw, size) { while (size > 16 && width(s, size) > maxw) size -= 1; return size; }
  // a label with its value on a dotted line; xr = right edge, w = total width
  function field(label, key, xr, y, w) {
    var lw = txt(label, xr, y, 27, BLACK, 'right', true) + 12, v = val(key), room = w - lw - 10;
    dots(xr - w, xr - lw - 4, y + 14);
    if (v !== '') txt(v, xr - lw - 8, y - 2, fit(String(v), room, 28), INK, 'right');
  }
  function row(y, items) {
    var x = XR - 22;
    items.forEach(function (it) { field(it[0], it[1], x, y, it[2]); x -= it[2] + 24; });
  }
  function square(x, y, on) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(x - 24, y - 12, 24, 24); if (on) { ctx.fillStyle = INK; ctx.fillRect(x - 20, y - 8, 16, 16); } ctx.restore(); }
  // options laid right to left: "label  ☐ a  ☐ b ..."
  function options(label, key, xr, y, size) {
    var x = xr; if (label) x -= txt(label, x, y, 27, BLACK, 'right', true) + 18;
    CH[key] && Object.keys(CH[key]).forEach(function (v) {
      if (v === '') return;
      square(x, y, String(val(key)) === v); x -= 34;
      x -= txt(CH[key][v], x, y, size || 25, BLACK, 'right') + 26;
    });
  }
  function paragraph(parts, x1, x0, y, lineH, size) {
    var words = [];
    parts.forEach(function (p) {
      if (p.t != null) String(p.t).split(' ').forEach(function (w) { if (w) words.push({ text: w, ink: false }); });
      else { var v = fa(p.v); if (v) v.split(' ').forEach(function (w) { words.push({ text: w, ink: true }); }); }
    });
    var space = size * 0.32, x = x1, line = y;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
    words.forEach(function (w) {
      ctx.font = (w.ink ? '' : 'bold ') + size + 'px ' + FONT;
      var wd = ctx.measureText(w.text).width;
      if (x - wd < x0) { x = x1; line += lineH; }
      ctx.fillStyle = w.ink ? INK : BLACK; ctx.fillText(w.text, x, line); x -= wd + space;
    });
    ctx.restore(); return line;
  }
  function head(n) {
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 5; ctx.strokeRect(50, 50, W - 100, H - 100); ctx.lineWidth = 2; ctx.strokeRect(62, 62, W - 124, H - 124); ctx.restore();
    txt(String(n), W / 2, H - 70, 30, BLACK, 'center', true);
  }

  // ---------- page 1 ----------
  function page1() {
    head(1);
    txt('بسمه تعالی', W / 2, 135, 32, BLACK, 'center', true); txt('پروانه ساختمان', W / 2, 215, 80, BLACK, 'center', true);
    box(290, 640);
    row(345, [['نوع پروانه:', 'kind', 520], ['شماره پروانه:', 'permit_no', 520]]);
    row(410, [['عوارض زیربنا طبق فیش شماره:', 'fee_slip_no', 620], ['مورخ:', 'fee_slip_date', 420]]);
    row(475, [['عوارض پذیره طبق فیش شماره:', 'entry_slip_no', 620], ['مورخ:', 'entry_slip_date', 420]]);
    row(540, [['بیمه کارگران طبق فیش شماره:', 'ins_slip_no', 620], ['کد:', 'ins_code', 420]]);
    row(605, [['تاریخ صدور پروانه:', 'issue_date', 420], ['تاریخ اتمام عملیات ساختمانی:', 'finish_date', 380], ['سال:', 'finish_year', 160]]);
    box(675, 765); txt('اعتبار این پروانه جهت شروع عملیات ساختمانی یک سال از تاریخ صدور می‌باشد.', W / 2, 720, 29, BLACK, 'center', true);
    box(800, 1330);
    row(850, [['شماره پلاک ثبتی:', 'registry_plot', 420], ['بخش:', 'section', 320], ['قطعه:', 'lot', 180], ['حوزه:', 'zone', 180]]);
    row(915, [['نام و نام خانوادگی مالک آقای/خانم:', 'owner', 700], ['فرزند:', 'father', 400]]);
    row(980, [['شماره شناسنامه:', 'id_number', 330], ['صادره از:', 'issued_at', 330], ['کد ملی:', 'national_id', 360]]);
    row(1045, [['نام و نام خانوادگی وکیل قانونی:', 'lawyer', 680], ['با شماره وکالتنامه:', 'lawyer_no', 420]]);
    options('نوع مالکیت:', 'ownership', XR - 22, 1110);
    row(1175, [['نشانی ملک:', 'address', 1230]]);
    row(1240, [['کوچه:', 'alley', 520], ['پلاک:', 'plot_no', 260], ['کد پستی:', 'postal_code', 380]]);
    box(1370, 1880);
    row(1420, [['۱- آقای مهندس ناظر ساختمانی:', 'sup_name', 1230]]);
    row(1485, [['دارای پروانه اشتغال به شماره:', 'sup_license', 700], ['شماره امضاء:', 'sup_sign', 500]]);
    row(1550, [['محاسب ۱- خانم/آقای:', 'calc_name', 700], ['پروانه:', 'calc_license', 250], ['امضاء:', 'calc_sign', 230]]);
    row(1615, [['تاسیسات ۲- خانم/آقای:', 'inst_name', 700], ['پروانه:', 'inst_license', 250], ['امضاء:', 'inst_sign', 230]]);
    row(1680, [['ناظر معماری:', 'arch_name', 700], ['پروانه:', 'arch_license', 250], ['امضاء:', 'arch_sign', 230]]);
  }

  // ---------- page 2 ----------
  function page2() {
    head(2);
    box(100, 300);
    options('وضعیت موجود ملک:', 'existing', XR - 22, 150, 24);
    options('زمین:', 'land', XR - 22, 215, 24); txt('تعداد اصله درخت:', 560, 215, 27, BLACK, 'right', true); txt(val('trees'), 380, 213, 28, INK, 'right');
    var cols = [[1310, 1150], [1150, 880], [880, 610], [610, 340], [340, 90]], heads = ['', 'ابعاد مندرج در سند', 'ابعاد موجود روی زمین', 'عرض گذر (متر)', 'ابعاد باقی‌مانده بعد از رعایت برهای اصلاحی'];
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, 330, XR - XL, 80 + 4 * 78); ctx.restore();
    cols.forEach(function (c, i) { if (i) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(c[0], 330); ctx.lineTo(c[0], 330 + 80 + 4 * 78); ctx.stroke(); ctx.restore(); } if (heads[i]) txt(heads[i], (c[0] + c[1]) / 2, 370, 22, BLACK, 'center', true); });
    var names = { north: 'شمالاً', south: 'جنوباً', east: 'شرقاً', west: 'غرباً' }, y = 410;
    data.sides.forEach(function (s) {
      ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, y); ctx.lineTo(XR, y); ctx.stroke(); ctx.restore();
      txt(names[s], 1230, y + 39, 27, BLACK, 'center', true);
      ['deed', 'actual', 'passage', 'after'].forEach(function (k, i) { var v = val('sd_' + s + '_' + k); if (v !== '') txt(v + ' متر', (cols[i + 1][0] + cols[i + 1][1]) / 2, y + 39, 27, INK, 'center'); });
      y += 78;
    });
    var yy = 770;
    yy = paragraph([{ t: 'مساحت زمین مطابق سند' }, { v: val('deed_area') || '......' }, { t: 'متر مربع / مساحت زمین بعد از رعایت برهای اصلاحی' }, { v: val('area_after') || '......' },
                    { t: 'متر مربع / میزان تراکم مجاز' }, { v: val('density_pct') || '......' }, { t: 'درصد' }], XR - 22, XL + 20, yy, 56, 28) + 62;
    yy = paragraph([{ t: 'مساحت مجاز ساخت' }, { v: val('built_allowed') || '......' }, { t: 'متر مربع می‌باشد.' }], XR - 22, XL + 20, yy, 56, 28) + 62;
    yy = paragraph([{ t: 'میزان مجاز اشغال زمین' }, { v: val('occupancy_m2') || '......' }, { t: 'متر مربع می‌باشد.' }], XR - 22, XL + 20, yy, 56, 28) + 62;
    paragraph([{ t: 'مساحت فضاهای (زیرزمین، پیلوت، خرپشته) در صورت مجاز بودن احداث آن برابر ضوابط و مقررات مصوب طرح هادی به مجموع مساحت مجاز ساخت طبقات افزوده می‌شود.' }], XR - 22, XL + 20, yy, 48, 24);
    box(1130, 1880);
    txt('کروکی دقیق محل ملک و گذرهای مجاور', XR - 40, 1180, 28, BLACK, 'right', true);
    txt('کد نقشه هوایی:', 560, 1180, 26, BLACK, 'right', true); txt(val('aerial_code'), 380, 1178, 28, INK, 'right');
    txt('شمال', XL + 130, 1250, 30, BLACK, 'center', true);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(XL + 130, 1380); ctx.lineTo(XL + 130, 1280); ctx.moveTo(XL + 100, 1310); ctx.lineTo(XL + 130, 1280); ctx.lineTo(XL + 160, 1310); ctx.stroke(); ctx.restore();
    txt('(نقشه‌ی ملک را از صفحه‌ی فرم‌ها چاپ و اینجا بچسبانید)', W / 2, 1560, 24, '#9ca3af', 'center');
  }

  // ---------- page 3 ----------
  function page3() {
    head(3);
    box(100, 440);
    options('نوع استفاده‌ی مجاز (طرح هادی):', 'usage', XR - 22, 145, 20);
    txt(val('usage') === 'other' ? val('usage_other') : '', 200, 145, 22, INK, 'right');
    paragraph([{ t: 'میزان تراکم مجاز' }, { v: val('density_pct') || '......' }, { t: 'درصد، مساحت ساخت مجاز بر اساس میزان تراکم' }, { v: val('built_allowed') || '......' }, { t: 'متر مربع می‌باشد. میزان مجاز اشغال زمین' }, { v: val('occupancy_m2') || '......' }, { t: 'متر مربع است.' }], XR - 22, XL + 20, 200, 50, 25);
    options('محل یا سمت احداث بنا:', 'position', XR - 22, 305, 24);
    options('نوع اسکلت ساختمان:', 'structure', XR - 22, 355, 24);
    options('نوع سقف:', 'roof', XR - 22, 405, 24);
    txt('گروه ساختمانی جهت صرفه‌جویی در انرژی:', XR - 22, 480, 25, BLACK, 'right', true);
    box(505, 680);
    var en = CH.energy || {}, ev = String(val('energy'));
    ['1', '2', '3', '4'].forEach(function (k, i) { square(XR - 34, 545 + i * 38, ev === k); txt(k + '- ' + (en[k] || ''), XR - 70, 545 + i * 38, 23, BLACK, 'right'); });
    options('چک لیست آیین‌نامه‌ی زلزله (۲۸۰۰ ایران) تکمیل گردیده است:', 'checklist', XR - 22, 725, 23);
    options('مصالح مورد استفاده در نما:', 'material', XR - 22, 775, 23);
    paragraph([{ t: 'تعداد اصله درخت قابل قطع' }, { v: val('trees_cut') || '......' }, { t: 'که عوارض متعلقه آن طی فیش شماره' }, { v: val('fee_no_cut') || '......' }, { t: 'پرداخت شده است.' }], XR - 22, XL + 20, 830, 46, 24);
    var tx = [[1310, 1090], [1090, 920], [920, 760], [760, 600], [600, 340], [340, 90]], head3 = ['', 'تعداد', 'مساحت (م²)', 'ارتفاع (م)', 'مسکونی (م²)', 'سایر (م²)'];
    var names = { basement: 'زیرزمین', ground: 'همکف', mezz: 'نیم‌طبقه', first: 'اول', attic: 'خرپشته' }, y0 = 880, rh = 54, rows = data.floors.length + 2;
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, y0, XR - XL, rh * rows); ctx.restore();
    tx.forEach(function (c, i) { if (i) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(c[0], y0); ctx.lineTo(c[0], y0 + rh * rows); ctx.stroke(); ctx.restore(); } if (head3[i]) txt(head3[i], (c[0] + c[1]) / 2, y0 + rh / 2, 23, BLACK, 'center', true); });
    var sum = { count: 0, area: 0, res: 0, other: 0 };
    data.floors.forEach(function (fl, r) {
      var y = y0 + rh * (r + 1);
      ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, y); ctx.lineTo(XR, y); ctx.stroke(); ctx.restore();
      txt(names[fl], 1200, y + rh / 2, 25, BLACK, 'center', true);
      ['count', 'area', 'height', 'res', 'other'].forEach(function (k, i) {
        var v = val('fl_' + fl + '_' + k); if (v === '') return;
        txt(v, (tx[i + 1][0] + tx[i + 1][1]) / 2, y + rh / 2, 25, INK, 'center');
        var n = parseFloat(String(v).replace(/[^\d.]/g, '')); if (sum[k] != null && isFinite(n)) sum[k] += n;
      });
    });
    var ys = y0 + rh * (rows - 1);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, ys); ctx.lineTo(XR, ys); ctx.stroke(); ctx.restore();
    txt('جمع', 1200, ys + rh / 2, 25, BLACK, 'center', true);
    ['count', 'area', null, 'res', 'other'].forEach(function (k, i) { if (k && sum[k]) txt(Math.round(sum[k] * 100) / 100, (tx[i + 1][0] + tx[i + 1][1]) / 2, ys + rh / 2, 25, INK, 'center'); });
    var y = y0 + rh * rows + 45;
    paragraph([{ t: 'تعداد' }, { v: val('parking') || '......' }, { t: 'واحد پارکینگ مورد نیاز می‌باشد که در بنا تامین گردد.' }], XR - 22, XL + 20, y, 46, 25);
    txt('ملاحظات:', XR - 22, y + 55, 26, BLACK, 'right', true);
    var notes = '۱- این پروانه به منزله‌ی سند مالکیت نمی‌باشد. ۲- شروع عملیات ساختمانی باید با اطلاع ناظر فنی صورت گیرد و تمام مراحل احداث بنا با نظارت ناظر و بر اساس آیین‌نامه زلزله (استاندارد ۲۸۰۰ ایران) اجرا گردد. ۳- عوارض زیربنای ساختمان به‌طور علی‌الحساب اخذ گردیده و هزینه آماده‌سازی و آسفالت به عهده بنیاد مسکن انقلاب اسلامی شهرستان می‌باشد. ۴- ' + (val('bonyad_ref') || '......') + ' ۵- متقاضی مکلف است بر و کف ملک را از بنیاد مسکن انقلاب اسلامی تحویل گیرد.' + (val('notes_extra') ? ' ' + val('notes_extra') : '');
    paragraph([{ t: notes }], XR - 22, XL + 20, y + 105, 38, 22);
    txt('نام و امضاء دهیار', 360, 1880, 26, BLACK, 'center', true); txt(val('dehyari_name'), 360, 1840, 26, INK, 'center');
    txt('نام و امضاء مسئول فنی دهیاری', 1030, 1880, 26, BLACK, 'center', true); txt(val('tech_name'), 1030, 1840, 26, INK, 'center');
  }

  // ---------- page 4: amendments and changes of the permit ----------
  function page4() {
    head(4);
    txt('اصلاحات و تغییرات پروانه ساختمان', W / 2, 150, 54, BLACK, 'center', true);
    box(210, 330);
    paragraph([{ t: 'در صورت درخواست مالک به تغییر نقشه و پروانه صادره از نظر افزایش یا کاهش واحدها در سطح، تغییر سطوح داخلی، تغییر کاربری و سایر تغییرات و اصلاحات مجاز در چارچوب قوانین، مقررات و ضوابط مصوب طرح هادی روستا این قسمت توسط دهیاری تکمیل می‌شود.' }], XR - 22, XL + 20, 250, 44, 24);
    row(390, [['تاریخ انجام تغییرات:', 'am_date', 700]]);
    row(450, [['عوارض زیربنا طبق فیش شماره:', 'am_fee_slip_no', 700], ['کد:', 'am_code', 360]]);
    row(510, [['عوارض پذیره طبق فیش شماره:', 'am_entry_slip_no', 700]]);
    row(570, [['بیمه کارگران طبق فیش شماره:', 'am_ins_slip_no', 620], ['عوارض پارکینگ:', 'am_parking_slip_no', 420]]);
    var cols = [[1310, 1150], [1150, 880], [880, 610], [610, 340], [340, 90]], heads = ['', 'ابعاد مندرج در سند', 'ابعاد موجود روی زمین', 'عرض گذر و شماره پروفیل', 'ابعاد باقی‌مانده بعد از رعایت برهای اصلاحی'], y0 = 630;
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, y0, XR - XL, 80 + 4 * 62); ctx.restore();
    cols.forEach(function (c, i) { if (i) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(c[0], y0); ctx.lineTo(c[0], y0 + 80 + 4 * 62); ctx.stroke(); ctx.restore(); } if (heads[i]) txt(heads[i], (c[0] + c[1]) / 2, y0 + 40, 20, BLACK, 'center', true); });
    var nm = { north: 'شمالاً', east: 'شرقاً', south: 'جنوباً', west: 'غرباً' }, y = y0 + 80;
    ['north', 'east', 'south', 'west'].forEach(function (s) {
      ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, y); ctx.lineTo(XR, y); ctx.stroke(); ctx.restore();
      txt(nm[s], 1230, y + 31, 26, BLACK, 'center', true);
      ['deed', 'actual', 'passage', 'after'].forEach(function (k, i) { var v = val('am_sd_' + s + '_' + k); if (v !== '') txt(v + ' متر', (cols[i + 1][0] + cols[i + 1][1]) / 2, y + 31, 25, INK, 'center'); });
      y += 62;
    });
    var yy = paragraph([{ t: 'مساحت زمین مطابق سند' }, { v: val('am_deed_area') || '......' }, { t: 'متر مربع / مساحت زمین بعد از رعایت برهای اصلاحی' }, { v: val('am_area_after') || '......' }, { t: 'متر مربع / میزان تراکم مجاز' }, { v: val('am_density_pct') || '......' }, { t: 'درصد' }], XR - 22, XL + 20, y0 + 80 + 4 * 62 + 60, 52, 26) + 60;
    paragraph([{ t: 'مساحت مجاز ساخت' }, { v: val('am_built') || '......' }, { t: 'متر مربع / میزان مجاز اشغال زمین' }, { v: val('am_occupancy') || '......' }, { t: 'متر مربع.' }], XR - 22, XL + 20, yy, 52, 26);
    var tx = [[1310, 1090], [1090, 920], [920, 760], [760, 600], [600, 340], [340, 90]], head3 = ['', 'تعداد', 'مساحت (م²)', 'ارتفاع (م)', 'مسکونی (م²)', 'سایر (م²)'];
    var names = { basement: 'زیرزمین', ground: 'همکف', mezz: 'نیم‌طبقه', first: 'اول', attic: 'خرپشته' }, t0 = 1290, rh = 54, rows = data.floors.length + 2;
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2.5; ctx.strokeRect(XL, t0, XR - XL, rh * rows); ctx.restore();
    tx.forEach(function (c, i) { if (i) { ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(c[0], t0); ctx.lineTo(c[0], t0 + rh * rows); ctx.stroke(); ctx.restore(); } if (head3[i]) txt(head3[i], (c[0] + c[1]) / 2, t0 + rh / 2, 23, BLACK, 'center', true); });
    var sum = { count: 0, area: 0, res: 0, other: 0 };
    data.floors.forEach(function (fl, r) {
      var yr = t0 + rh * (r + 1);
      ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, yr); ctx.lineTo(XR, yr); ctx.stroke(); ctx.restore();
      txt(names[fl], 1200, yr + rh / 2, 25, BLACK, 'center', true);
      ['count', 'area', 'height', 'res', 'other'].forEach(function (k, i) { var v = val('am_fl_' + fl + '_' + k); if (v === '') return; txt(v, (tx[i + 1][0] + tx[i + 1][1]) / 2, yr + rh / 2, 25, INK, 'center'); var n = parseFloat(String(v).replace(/[^\d.]/g, '')); if (sum[k] != null && isFinite(n)) sum[k] += n; });
    });
    var ys = t0 + rh * (rows - 1);
    ctx.save(); ctx.strokeStyle = BLACK; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(XL, ys); ctx.lineTo(XR, ys); ctx.stroke(); ctx.restore();
    txt('جمع', 1200, ys + rh / 2, 25, BLACK, 'center', true);
    ['count', 'area', null, 'res', 'other'].forEach(function (k, i) { if (k && sum[k]) txt(Math.round(sum[k] * 100) / 100, (tx[i + 1][0] + tx[i + 1][1]) / 2, ys + rh / 2, 25, INK, 'center'); });
    txt('ملاحظات:', XR - 22, t0 + rh * rows + 50, 26, BLACK, 'right', true);
    paragraph([{ v: val('am_notes') }], XR - 22, XL + 20, t0 + rh * rows + 105, 44, 25);
    txt('نام و امضاء دهیار', 360, 1880, 26, BLACK, 'center', true); txt(val('dehyari_name'), 360, 1840, 26, INK, 'center');
    txt('نام و امضاء مسئول فنی دهیاری', 1030, 1880, 26, BLACK, 'center', true); txt(val('tech_name'), 1030, 1840, 26, INK, 'center');
  }

  var DRAW = { 1: page1, 2: page2, 3: page3, 4: page4 };
  function draw(n) { page = n || page; ctx.clearRect(0, 0, W, H); DRAW[page](); }
  function pageCanvas(n) { var keep = page; draw(n); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  var form = document.getElementById('pfl-form');
  function read() { document.querySelectorAll('#pfl-form [name^="f_"], #pfl-amend [name^="f_"]').forEach(function (el) { F[el.name.slice(2)] = el.value; }); }
  function refresh() { read(); draw(); }
  [form, document.getElementById('pfl-amend')].forEach(function (f) { if (f) { f.addEventListener('input', refresh); f.addEventListener('change', refresh); } });
  function setTab(n) { document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-page') === String(n)); }); draw(n); }
  document.querySelectorAll('.pff-tabs button').forEach(function (b) { b.addEventListener('click', function () { setTab(parseInt(b.getAttribute('data-page'), 10)); }); });

  function on(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('click', fn); }
  async function download(list, name) {
    var jpgs = []; for (var i = 0; i < list.length; i++) jpgs.push(await PdfLite.toJpeg(pageCanvas(list[i])));
    PdfLite.save(PdfLite.make(jpgs, W, H), name);
  }
  on('pfl-dl-this', function () { download([page], 'permit-page' + page + '-' + data.file + '.pdf'); });
  on('pfl-dl-all', function () { download([1, 2, 3], 'building-permit-' + data.file + '.pdf'); });
  on('pfl-print', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style');
    doc.title = 'چاپ پروانه ساختمان'; style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm;page-break-after:always}';
    doc.head.appendChild(style);
    [1, 2, 3].forEach(function (n) { var im = doc.createElement('img'); im.src = pageCanvas(n).toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); });
    win.focus(); setTimeout(function () { win.print(); }, 400);
  });
  document.fonts.load('30px Vazirmatn').then(function () { return document.fonts.load('bold 30px Vazirmatn'); }).then(function () {
    document.getElementById('pff-loading').hidden = true; refresh();
  });
})();
