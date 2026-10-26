/* A minimal PDF writer: one JPEG per A4 page (used to download the permit forms drawn on a canvas). */
(function () {
  'use strict';
  function toJpeg(canvas) {
    return new Promise(function (resolve) {
      canvas.toBlob(function (blob) { blob.arrayBuffer().then(function (buf) { resolve(new Uint8Array(buf)); }); }, 'image/jpeg', 0.92);
    });
  }
  function make(pages, W, H) {
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
  window.PdfLite = { toJpeg: toJpeg, make: make, save: save };
})();
