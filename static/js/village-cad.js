/* The plan as drawn in AutoCAD, on the web map: filled and hatched areas, lines and the plan's texts, each with the
   drawing's own colour, line weight and line type. One canvas tile layer over a spatial index, so 25 000 shapes stay
   fast. Data: /gis/<slug>/cad/ (built by scripts/gis/build_cad_layer.py). All text is drawn with fillText, never as HTML. */
(function () {
  'use strict';

  const TILE = 256;
  const GRID = 96;                                   // cells per side of the spatial index
  const DASHES = { d: [8, 5], o: [1.5, 4], c: [14, 4, 2, 4] };
  const mercX = (lon) => (lon + 180) / 360;
  const mercY = (lat) => { const s = Math.sin(lat * Math.PI / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };

  function project(flat) {
    const out = new Float64Array(flat.length);
    for (let i = 0; i < flat.length; i += 2) { out[i] = mercX(flat[i]); out[i + 1] = mercY(flat[i + 1]); }
    return out;
  }

  function bboxOf(arrays) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    arrays.forEach((a) => {
      for (let i = 0; i < a.length; i += 2) {
        if (a[i] < x0) x0 = a[i]; if (a[i] > x1) x1 = a[i];
        if (a[i + 1] < y0) y0 = a[i + 1]; if (a[i + 1] > y1) y1 = a[i + 1];
      }
    });
    return [x0, y0, x1, y1];
  }

  function patternCanvas(kind, angle, spacing, color) {
    // a small tile whose lines repeat seamlessly: 45 / 135 degrees, horizontal, vertical, a cross or dots
    const s = Math.max(3, Math.round(spacing));
    const c = document.createElement('canvas');
    c.width = c.height = s;
    const g = c.getContext('2d');
    g.strokeStyle = color; g.fillStyle = color; g.lineWidth = 1;
    const diag = (flip) => {
      g.beginPath();
      if (flip) { g.moveTo(0, s); g.lineTo(s, 0); g.moveTo(-1, 1); g.lineTo(1, -1); g.moveTo(s - 1, s + 1); g.lineTo(s + 1, s - 1); }
      else { g.moveTo(0, 0); g.lineTo(s, s); g.moveTo(-1, s - 1); g.lineTo(1, s + 1); g.moveTo(s - 1, -1); g.lineTo(s + 1, 1); }
      g.stroke();
    };
    const a = ((angle % 180) + 180) % 180;
    if (kind === 'o') { g.beginPath(); g.arc(s / 2, s / 2, 0.9, 0, 6.3); g.fill(); }
    else if (kind === 'x') { diag(false); diag(true); }
    else if (a > 30 && a < 60) diag(false);
    else if (a > 120 && a < 150) diag(true);
    else if (a >= 60 && a <= 120) { g.beginPath(); g.moveTo(s / 2, 0); g.lineTo(s / 2, s); g.stroke(); }
    else { g.beginPath(); g.moveTo(0, s / 2); g.lineTo(s, s / 2); g.stroke(); }
    return c;
  }

  const CadLayer = L.GridLayer.extend({
    options: { tileSize: TILE, maxNativeZoom: 21, maxZoom: 21, minZoom: 12, updateWhenIdle: true, keepBuffer: 2, pane: 'tilePane' },

    initialize(data, options) {
      L.setOptions(this, options);
      this.layers = data.layers;
      this.bg = options.background || '#15181c';
      this.patterns = new Map();
      this.hidden = new Set();
      this.items = data.items.map((raw) => this.prepare(raw));
      const all = this.items.map((it) => it.box);
      this.box = bboxOf([].concat(...all.map((b) => [b[0], b[1], b[2], b[3]])).length ? [new Float64Array(all.flatMap((b) => [b[0], b[1], b[2], b[3]]))] : [new Float64Array([0, 0, 1, 1])]);
      this.index = new Map();
      this.items.forEach((it, i) => {
        const x0 = this.cell(it.box[0], 0), x1 = this.cell(it.box[2], 0), y0 = this.cell(it.box[1], 1), y1 = this.cell(it.box[3], 1);
        for (let gx = x0; gx <= x1; gx += 1) for (let gy = y0; gy <= y1; gy += 1) {
          const key = gx * 1000 + gy;
          const list = this.index.get(key);
          if (list) list.push(i); else this.index.set(key, [i]);
        }
      });
    },

    setHidden(names) { this.hidden = names; this.redraw(); },

    cell(v, axis) {
      const lo = this.box[axis], hi = this.box[axis + 2];
      return Math.max(0, Math.min(GRID - 1, Math.floor(((v - lo) / (hi - lo || 1)) * GRID)));
    },

    prepare(raw) {
      const layer = this.layers[raw.l];
      const it = { k: raw.k, color: raw.c || layer.c, name: layer.n };
      if (raw.k === 'h') {
        it.rings = raw.r.map(project);
        it.box = bboxOf(it.rings);
        it.p = raw.p || ''; it.a = raw.a || 0; it.s = raw.s || 0;
      } else if (raw.k === 'l') {
        it.pts = project(raw.p);
        it.box = bboxOf([it.pts]);
        it.w = raw.w || 1; it.d = raw.d || '';
      } else {
        const x = mercX(raw.x), y = mercY(raw.y);
        it.x = x; it.y = y; it.text = raw.s; it.h = raw.h; it.rot = raw.a || 0;
        const r = Math.max(raw.s.length * raw.h * 0.7, raw.h) / 40075016;       // metres -> world fraction
        it.box = [x - r, y - r, x + r, y + r];
      }
      return it;
    },

    createTile(coords) {
      const tile = L.DomUtil.create('canvas', 'leaflet-tile');
      const size = this.getTileSize();
      tile.width = size.x; tile.height = size.y;
      const ctx = tile.getContext('2d');
      const z = coords.z, scale = TILE * Math.pow(2, z);
      const ox = coords.x * TILE, oy = coords.y * TILE;
      const wx0 = coords.x / Math.pow(2, z), wy0 = coords.y / Math.pow(2, z), span = 1 / Math.pow(2, z);
      const metresPerPixel = 40075016 * Math.cos(this.centreLat(wy0)) / scale;
      const pxPerMetre = 1 / metresPerPixel;
      const pad = 24 / scale;                                      // text and wide strokes spill over the tile edge
      const gx0 = this.cell(wx0 - pad, 0), gx1 = this.cell(wx0 + span + pad, 0), gy0 = this.cell(wy0 - pad, 1), gy1 = this.cell(wy0 + span + pad, 1);
      const seen = new Set();
      const todo = [];
      for (let gx = gx0; gx <= gx1; gx += 1) for (let gy = gy0; gy <= gy1; gy += 1) {
        (this.index.get(gx * 1000 + gy) || []).forEach((i) => { if (!seen.has(i)) { seen.add(i); todo.push(i); } });
      }
      todo.sort((a, b) => a - b);
      const draw = { h: [], l: [], t: [] };
      todo.forEach((i) => {
        const it = this.items[i];
        if (it.box[2] < wx0 - pad || it.box[0] > wx0 + span + pad || it.box[3] < wy0 - pad || it.box[1] > wy0 + span + pad) return;
        if (this.hidden.has(it.name) || this.hidden.has(`${it.name}|${it.color}`)) return;
        draw[it.k].push(it);
      });
      const px = (w, o) => w * scale - o;
      // areas: the fill first, then the hatch lines, so the colour of a zone is not hidden by the pattern of another
      draw.h.forEach((it) => this.hatch(ctx, it, px, ox, oy, pxPerMetre, coords));
      draw.l.forEach((it) => this.line(ctx, it, px, ox, oy, scale));
      draw.t.forEach((it) => this.text(ctx, it, px, ox, oy, pxPerMetre));
      return tile;
    },

    centreLat(wy) { return Math.atan(Math.sinh(Math.PI * (1 - 2 * wy))); },

    path(ctx, rings, px, ox, oy, close) {
      ctx.beginPath();
      rings.forEach((ring) => {
        for (let i = 0; i < ring.length; i += 2) {
          const x = px(ring[i], ox), y = px(ring[i + 1], oy);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        if (close) ctx.closePath();
      });
    },

    hatch(ctx, it, px, ox, oy, pxPerMetre, coords) {
      const wide = (it.box[2] - it.box[0]) * TILE * Math.pow(2, coords.z), high = (it.box[3] - it.box[1]) * TILE * Math.pow(2, coords.z);
      if (wide < 1 && high < 1) return;
      this.path(ctx, it.rings, px, ox, oy, true);
      if (!it.p) { ctx.fillStyle = it.color; ctx.fill('evenodd'); return; }
      const spacing = it.s * pxPerMetre;
      if (spacing < 3.2) { ctx.globalAlpha = 0.45; ctx.fillStyle = it.color; ctx.fill('evenodd'); ctx.globalAlpha = 1; return; }
      const key = `${it.p}|${Math.round(it.a)}|${Math.round(spacing)}|${it.color}`;
      let pattern = this.patterns.get(key);
      if (!pattern) { pattern = ctx.createPattern(patternCanvas(it.p, it.a, spacing, it.color), 'repeat'); this.patterns.set(key, pattern); }
      const s = Math.max(3, Math.round(spacing));
      const shiftX = -(ox % s), shiftY = -(oy % s);          // the pattern is anchored to the world, not to each tile
      ctx.save();
      ctx.clip('evenodd');
      ctx.translate(shiftX, shiftY);
      ctx.fillStyle = pattern;
      ctx.fillRect(-shiftX, -shiftY, TILE + s, TILE + s);
      ctx.restore();
    },

    line(ctx, it, px, ox, oy, scale) {
      const n = it.pts.length / 2;
      if (n < 2) return;
      if ((it.box[2] - it.box[0]) * scale < 0.6 && (it.box[3] - it.box[1]) * scale < 0.6) return;
      ctx.beginPath();
      for (let i = 0; i < n; i += 1) {
        const x = px(it.pts[2 * i], ox), y = px(it.pts[2 * i + 1], oy);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = it.color;
      ctx.lineWidth = it.w;
      ctx.setLineDash(it.d ? DASHES[it.d] : []);
      ctx.stroke();
    },

    text(ctx, it, px, ox, oy, pxPerMetre) {
      const size = it.h * pxPerMetre;
      if (size < 5) return;
      ctx.save();
      ctx.translate(px(it.x, ox), px(it.y, oy));
      ctx.rotate(-it.rot * Math.PI / 180);
      ctx.font = `600 ${Math.min(size, 80)}px Vazirmatn, Tahoma, sans-serif`;
      ctx.direction = 'rtl';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'alphabetic';
      ctx.lineWidth = 2;
      ctx.lineJoin = 'round';
      ctx.strokeStyle = 'rgba(0,0,0,.35)';
      ctx.strokeText(it.text, 0, 0);
      ctx.fillStyle = it.color;
      ctx.fillText(it.text, 0, 0);
      ctx.restore();
    },
  });

  window.VillageCad = { create: (data, options) => new CadLayer(data, options) };
})();
