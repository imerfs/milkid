/* Permit file, supervision: forms 8-13 drawn over their blank forms from the file's data (json_script #pfs-data) and the form on
   the page, downloaded as PDF or printed. The supervising engineer inspects, stamps and signs the printed sheet by hand. */
(function () {
  'use strict';
  var data = JSON.parse(document.getElementById('pfs-data').textContent);
  var canvas = document.getElementById('pff-canvas'), ctx = canvas.getContext('2d');
  var W = 1400, H = 2000, INK = '#0a1f6e', FONT = 'Vazirmatn, Tahoma, sans-serif', images = {}, page = data.now;
  var FA = '۰۱۲۳۴۵۶۷۸۹';
  function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }
  function put(text, b, size) {                        // b = [x0, x1, y]
    text = fa(text); if (!text) return;
    var s = size || 30;
    ctx.save(); ctx.direction = 'rtl'; ctx.textBaseline = 'middle'; ctx.fillStyle = INK; ctx.textAlign = 'center'; ctx.font = s + 'px ' + FONT;
    while (ctx.measureText(text).width > b[1] - b[0] && s > 14) { s -= 1; ctx.font = s + 'px ' + FONT; }
    ctx.fillText(text, (b[0] + b[1]) / 2, b[2]); ctx.restore();
  }
  function tick(cx, cy) {
    ctx.save(); ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(cx - 13, cy + 1); ctx.lineTo(cx - 4, cy + 12); ctx.lineTo(cx + 16, cy - 13); ctx.stroke(); ctx.restore();
  }
  var TOP = { number: [155, 250, 143], date: [155, 430, 188] };
  var ST = [[885, 1035, 960], [705, 815, 960], [310, 455, 960], [160, 240, 960], [885, 1030, 1022], [705, 815, 1022], [310, 425, 1022], [160, 240, 1022]];
  var SPEC = {
    8: { text: { village: [785, 990, 585], sup_name: [830, 1150, 645], sup_license: [350, 570, 645], sup_license_date: [155, 285, 645], permit_no: [360, 525, 707], permit_date: [155, 285, 707],
                 pledge_no: [700, 915, 768], owner: [155, 465, 768], dahestan: [480, 765, 828], section: [155, 410, 828], shahrestan: [910, 1125, 888], start_date: [600, 865, 888] },
         extra: function (f) { put(f.village, [785, 1055, 828]); } },
    9: { text: { permit_no: [600, 975, 497], permit_date: [155, 360, 497], owner: [660, 1035, 560], sup_name: [660, 1035, 710], sup_license: [160, 470, 710], pledge_no: [655, 985, 777],
                 use: [1000, 1115, 925], floors: [720, 860, 925], structure: [460, 605, 925], area: [155, 325, 925] }, notes: [165, 1120, 1545],
         marks: [[1060, 615, 452], [1122, 575, 338], [1184, 520, 350], [1245, 428, 181], [1305, 590, 341], [1365, 740, 527], [1425, 592, 334], [1487, 532, 286]], viol: [1607, 1085, 840] },
    10: { text: { permit_no: [700, 975, 505], permit_date: [705, 1020, 573], owner: [705, 1105, 640], sup_name: [780, 1030, 775], sup_license: [340, 585, 775], pledge_no: [925, 1160, 843],
                  use: [550, 1110, 976], floors: [160, 410, 976], structure: [550, 1120, 1043], area: [160, 400, 1043] }, notes: [165, 1120, 1577],
          marks: [[1205, 632, 473], [1267, 632, 473], [1328, 570, 355], [1450, 1117, 947], [1515, 558, 383]], viol: [1637, 1092, 776] },
    11: { text: { permit_no: [700, 975, 565], permit_date: [705, 1025, 623], owner: [705, 1105, 686], sup_name: [780, 1030, 833], sup_license: [340, 585, 833], pledge_no: [925, 1160, 900],
                  use: [555, 1110, 1032], floors: [160, 410, 1032], structure: [555, 1120, 1100], area: [160, 400, 1100] }, notes: [165, 1120, 1620],
          marks: [[1319, 1073, 862], [1380, 535, 348], [1440, 433, 212], [1500, 523, 356], [1561, 674, 503]], viol: [1683, 1092, 776] },
    12: { text: { permit_no: [700, 975, 565], permit_date: [705, 1025, 623], owner: [705, 1105, 686], sup_name: [660, 1035, 833], sup_license: [165, 435, 833], pledge_no: [660, 985, 900],
                  use: [555, 1110, 1032], floors: [160, 410, 1032], structure: [555, 1120, 1100], area: [160, 400, 1100] }, notes: [165, 1120, 1560],
          marks: [[1260, 560, 357], [1310, 560, 357], [1360, 560, 357], [1410, 560, 357], [1460, 560, 357], [1510, 560, 357]], viol: [1609, 1092, 776] },
    13: { text: { village: [820, 1085, 470], sup_name: [855, 1160, 532], father: [630, 775, 532], id_no: [160, 375, 532], issued_at: [905, 1145, 594], sup_license: [460, 585, 594],
                  license_date: [160, 355, 594], pledge_no: [590, 830, 655], end_date: [665, 870, 778], vote_no: [615, 825, 1533], req_permit_no: [812, 930, 1587],
                  req_permit_date: [612, 738, 1587], req_owner: [160, 350, 1587] },
          extra: function (f) { ['s1_no', 's1_date', 's2_no', 's2_date', 's3_no', 's3_date', 's4_no', 's4_date'].forEach(function (k, i) { put(f[k], ST[i]); }); } }
  };

  function drawForm(n) {
    var d = data.forms[String(n)], spec = SPEC[n], f = d.f;
    ctx.clearRect(0, 0, W, H); ctx.drawImage(images[n], 0, 0, W, H);
    put(f.number, TOP.number); put(f.date, TOP.date);
    Object.keys(spec.text).forEach(function (k) { put(f[k], spec.text[k]); });
    if (spec.extra) spec.extra(f);
    if (spec.marks) {
      spec.marks.forEach(function (m, i) { var c = d.c[String(i + 1)]; if (c === 'a') tick(m[1], m[0]); else if (c === 'b') tick(m[2], m[0]); });
      put(d.notes, spec.notes, 26);
      if (d.result === 'violation') tick(spec.viol[1], spec.viol[0]); else if (d.result === 'ok') tick(spec.viol[2], spec.viol[0]);
    }
  }
  function draw(n) { page = n || page; drawForm(page); }
  function pageCanvas(n) { var keep = page; draw(n); var c = document.createElement('canvas'); c.width = W; c.height = H; c.getContext('2d').drawImage(canvas, 0, 0); draw(keep); return c; }

  // the form on the page (only for the current form) feeds the preview as the inputs change
  var form = document.getElementById('pfs-form');
  function read() {
    if (!form) return;
    var d = data.forms[String(data.now)];
    form.querySelectorAll('input[name^="f_"]').forEach(function (el) { d.f[el.name.slice(2)] = el.value; });
    d.c = {}; form.querySelectorAll('input[type=radio][name^="c_"]:checked').forEach(function (el) { d.c[el.name.slice(2)] = el.value; });
    var notes = form.querySelector('[name=notes]'); if (notes) d.notes = notes.value;
    var res = form.querySelector('input[name=result]:checked'); d.result = res ? res.value : '';
  }
  if (form) { var again = function () { read(); draw(); }; form.addEventListener('input', again); form.addEventListener('change', again); }
  document.querySelectorAll('.pfs-tabs button').forEach(function (b) { b.addEventListener('click', function () {
    document.querySelectorAll('.pfs-tabs button').forEach(function (x) { x.classList.toggle('is-on', x === b); }); draw(parseInt(b.getAttribute('data-page'), 10)); }); });

  document.getElementById('pfs-dl').addEventListener('click', async function () {
    var jpg = await PdfLite.toJpeg(pageCanvas(page)); PdfLite.save(PdfLite.make([jpg], W, H), 'supervision-form' + page + '-' + data.file + '.pdf');
  });
  document.getElementById('pfs-print').addEventListener('click', function () {
    var win = window.open('', '_blank'); if (!win) return;
    var doc = win.document, style = doc.createElement('style'), im = doc.createElement('img'); doc.title = 'چاپ فرم نظارت';
    style.textContent = '@page{size:A4;margin:0}body{margin:0}img{display:block;width:210mm;height:297mm}'; doc.head.appendChild(style);
    im.src = pageCanvas(page).toDataURL('image/jpeg', 0.92); doc.body.appendChild(im); win.focus(); setTimeout(function () { win.print(); }, 400);
  });

  function load(src) { return new Promise(function (resolve, reject) { var im = new Image(); im.onload = function () { resolve(im); }; im.onerror = reject; im.src = src; }); }
  var nums = [8, 9, 10, 11, 12, 13];
  Promise.all(nums.map(function (n) { return load(data.blank[String(n)]); }).concat([document.fonts.load('30px Vazirmatn')])).then(function (r) {
    nums.forEach(function (n, i) { images[n] = r[i]; });
    document.getElementById('pff-loading').hidden = true; read(); draw();
  });
})();
