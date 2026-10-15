/* Village web-GIS: blocks, plots (عرصه), buildings (اعیان), neighbourhoods, easements, land use, a timeline,
   locks, and the plot archive panel. All text from the server goes in with textContent / input.value, never as HTML. */
(function () {
  'use strict';

  const cfg = JSON.parse(document.getElementById('vm-config').textContent);
  const $ = (id) => document.getElementById(id);
  const app = $('vm-app');
  const canEdit = cfg.canEdit;
  const canLock = cfg.canLock;
  if (!canEdit) app.classList.add('vm-readonly');
  if (!canLock) app.classList.add('vm-nolock');

  const LAST_YEAR = cfg.years[cfg.years.length - 1];
  const ZONE_COLORS = { '1': '#f78e38', '2': '#fafa64', '3': '#a1c298', '4': '#2891c8', '5': '#e8141a', '6': '#8e44ad' };
  const EASEMENT_COLORS = { general: '#16a34a', quality: '#0ea5e9', qanat: '#a855f7', qanat_quality: '#6366f1', defense1: '#ef4444', defense2: '#f97316' };
  const STATUS = {
    empty: { fillColor: '#cbd5e1', color: '#475569' },
    filed: { fillColor: '#86efac', color: '#166534' },
    paid: { fillColor: '#60a5fa', color: '#1e3a8a' },
    estimated: { fillColor: '#fca5a5', color: '#7f1d1d' },
  };
  const toDigits = (s) => String(s).replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  const PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
  const faDigits = (value) => String(value).replace(/\d/g, (d) => PERSIAN_DIGITS[d]);
  const fa = (n) => faDigits(Number(n).toLocaleString('en-US')).replace(/,/g, '٬');   // no dependence on the browser's fa locale data

  // ---------- UTM <-> WGS84 (zone 40 N, the zone the drawings are in) ----------
  const UTM = (() => {
    const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, zone = 40;
    const e2 = f * (2 - f), ep2 = e2 / (1 - e2), lon0 = ((zone - 1) * 6 - 180 + 3) * Math.PI / 180;
    const rad = Math.PI / 180;
    function toLatLng(x, y) {
      const m = y / k0;
      const mu = m / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256));
      const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
      const phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu) + (21 * e1 * e1 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu) + (151 * e1 ** 3 / 96) * Math.sin(6 * mu);
      const n1 = a / Math.sqrt(1 - e2 * Math.sin(phi1) ** 2);
      const t1 = Math.tan(phi1) ** 2, c1 = ep2 * Math.cos(phi1) ** 2;
      const r1 = a * (1 - e2) / (1 - e2 * Math.sin(phi1) ** 2) ** 1.5;
      const d = (x - 500000) / (n1 * k0);
      const lat = phi1 - (n1 * Math.tan(phi1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d ** 4 / 24 + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d ** 6 / 720);
      const lng = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d ** 5 / 120) / Math.cos(phi1);
      return [lat / rad, lng / rad];
    }
    function fromLatLng(lat, lng) {
      const phi = lat * rad, lam = lng * rad;
      const n = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2), t = Math.tan(phi) ** 2, c = ep2 * Math.cos(phi) ** 2;
      const aa = Math.cos(phi) * (lam - lon0);
      const m = a * ((1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256) * phi - (3 * e2 / 8 + 3 * e2 * e2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * phi) + (15 * e2 * e2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * phi) - (35 * e2 ** 3 / 3072) * Math.sin(6 * phi));
      const x = k0 * n * (aa + (1 - t + c) * aa ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * ep2) * aa ** 5 / 120) + 500000;
      const y = k0 * (m + n * Math.tan(phi) * (aa * aa / 2 + (5 - t + 9 * c + 4 * c * c) * aa ** 4 / 24 + (61 - 58 * t + t * t + 600 * c - 330 * ep2) * aa ** 6 / 720));
      return [x, y];
    }
    return { toLatLng, fromLatLng };
  })();
  window.villageUTM = UTM;

  // ---------- map and base layers ----------
  const map = L.map('vm-map', { preferCanvas: true, zoomControl: true, minZoom: 12, maxZoom: 21, zoomSnap: 0.5, attributionControl: true });
  map.attributionControl.setPrefix(false);
  map.setView([0, 0], 15);                       // Leaflet needs a view before layers are added; the data sets the real one
  window.villageMap = map;                        // handy in the browser console when checking a deployment
  const canvas = L.canvas({ padding: 0.5 });
  const baseLayers = {};
  cfg.basemaps.forEach((b) => { baseLayers[b.id] = L.tileLayer(b.url, { maxZoom: b.maxZoom, maxNativeZoom: b.maxZoom, attribution: b.attribution }); });
  let currentBase = null;
  document.querySelectorAll('input[name=basemap]').forEach((radio) => radio.addEventListener('change', () => {
    if (currentBase) map.removeLayer(currentBase);
    currentBase = baseLayers[radio.value] || null;
    if (currentBase) { currentBase.addTo(map); currentBase.bringToBack(); }
  }));
  let traffic = null;
  const trafficBox = $('vm-traffic');
  if (cfg.trafficUrl) {
    trafficBox.addEventListener('change', () => {
      if (trafficBox.checked) { traffic = L.tileLayer(cfg.trafficUrl, { maxZoom: 19, opacity: 0.85 }).addTo(map); }
      else if (traffic) { map.removeLayer(traffic); traffic = null; }
    });
  }

  // ---------- state ----------
  const plots = new Map();             // id -> { layer, props, ring }
  const byCode = new Map();            // code -> [id]
  const blockLayers = new Map();       // block number -> layer
  const landUses = new Map();          // id -> { color, name, count }
  const groups = { plots: L.layerGroup(), blocks: L.layerGroup(), zones: L.layerGroup(), blockLabels: L.layerGroup(), plotLabels: L.layerGroup(), buildings: L.layerGroup() };
  const easementGroups = {};
  const buildingsOf = new Map();      // plot id -> its building layers
  const BUILDING_STYLE = { color: '#7c2d12', weight: 0.8, fillColor: '#c2410c', fillOpacity: 0.85 };
  const BUILDING_SELECTED = { color: '#facc15', weight: 2, fillColor: '#f97316', fillOpacity: 0.95 };
  let colorMode = 'use';
  let filter = 'all';
  let year = LAST_YEAR;
  let selectedId = null;
  let fitToVillage = null;
  let blockCount = 0;
  let easementsLoaded = false, buildingsLoaded = false;

  // ---------- what a plot looks like in the chosen year ----------
  function stateAt(p, y) {
    const exists = (!p.fy || p.fy <= y) && (!p.ly || y <= p.ly);
    const filed = Boolean(p.f) && (p.py == null ? y >= LAST_YEAR : p.py <= y);
    const paid = p.pay.some((v) => v && v <= y);
    const locked = p.lk.some(([s, e]) => s <= y && (!e || y < e));
    return { exists, filed, paid, locked };
  }

  function fillFor(p, st) {
    if (colorMode === 'use') { const use = landUses.get(p.lu); return use ? use.color : '#e5e7eb'; }
    if (colorMode === 'zone') return ZONE_COLORS[p.z] || '#e5e7eb';
    if (colorMode === 'easement') return p.h.length ? EASEMENT_COLORS[p.h[0]] : '#e5e7eb';
    if (p.e && !st.filed && !st.paid) return STATUS.estimated.fillColor;
    return st.paid ? STATUS.paid.fillColor : st.filed ? STATUS.filed.fillColor : STATUS.empty.fillColor;
  }

  function matchesFilter(p, st) {
    switch (filter) {
      case 'filed': return st.filed || st.paid;
      case 'empty': return !(st.filed || st.paid);
      case 'locked': return st.locked;
      case 'violation': return p.h.length > 0;
      case 'permit': return p.pm || (p.py != null && p.py <= year);
      case 'estimated': return p.e;
      default: return true;
    }
  }

  function styleFor(p) {
    const st = stateAt(p, year);
    if (!st.exists) return { opacity: 0, fillOpacity: 0, weight: 0 };
    const visible = matchesFilter(p, st);
    const style = { fillColor: fillFor(p, st), color: '#475569', weight: 1, dashArray: p.e ? '4 3' : null, fillOpacity: visible ? 0.78 : 0.06, opacity: visible ? 1 : 0.2 };
    if (colorMode === 'status' && p.e) style.color = '#7f1d1d';
    if (st.locked) { style.color = '#7f1d1d'; style.weight = 3; style.dashArray = null; style.opacity = 1; }
    return style;
  }

  function restyleBuildings(id, on) {
    (buildingsOf.get(id) || []).forEach((layer) => { layer.setStyle(on ? BUILDING_SELECTED : BUILDING_STYLE); if (on) layer.bringToFront(); });
  }

  function restyle(id) {
    const item = plots.get(id);
    if (!item) return;
    restyleBuildings(id, id === selectedId);
    if (id === selectedId) { item.layer.setStyle({ color: '#d97706', weight: 3, fillColor: '#fbbf24', fillOpacity: 0.92, dashArray: null, opacity: 1 }); item.layer.bringToFront(); return; }
    item.layer.setStyle(styleFor(item.props));
  }
  function restyleAll() { plots.forEach((_, id) => restyle(id)); updateStats(); updateLegend(); }

  // ---------- drawing ----------
  function ringOf(geometry) { return geometry.coordinates[0].map(([lng, lat]) => [lat, lng]); }

  function updateStats() {
    let estimated = 0, filed = 0, locked = 0, violating = 0, shown = 0;
    plots.forEach(({ props }) => {
      const st = stateAt(props, year);
      if (!st.exists) return;
      shown += 1;
      if (props.e) estimated += 1;
      if (st.filed || st.paid) filed += 1;
      if (st.locked) locked += 1;
      if (props.h.length) violating += 1;
    });
    $('vm-stats').textContent = `${fa(blockCount)} بلوک · ${fa(shown)} قطعه (${fa(estimated)} تقریبی) · ${fa(filed)} دارای بایگانی · ${fa(locked)} قفل‌شده · ${fa(violating)} متخلف از حریم`;
  }

  function render(data) {
    data.land_uses.forEach((u, i) => landUses.set(u.id, { color: u.color, name: u.name || `کاربری ${faDigits(i + 1)} (نام ثبت نشده)`, count: u.count }));
    blockCount = data.blocks.features.length;

    data.zones.features.forEach((f) => {
      const layer = L.geoJSON(f, { renderer: canvas, interactive: false, style: { color: ZONE_COLORS[f.properties.n] || '#000', weight: 4, fill: false, opacity: 0.95 } });
      groups.zones.addLayer(layer);
      groups.zones.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'vm-zone-label', opacity: 1 }).setContent(f.properties.name).setLatLng(layer.getBounds().getCenter()));
    });
    data.blocks.features.forEach((f) => {
      const layer = L.geoJSON(f, { renderer: canvas, interactive: false, style: { color: '#1e40af', weight: 1.6, fill: false, opacity: 0.8 } });
      groups.blocks.addLayer(layer);
      blockLayers.set(f.properties.n, layer);
      groups.blockLabels.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'vm-block-label', opacity: 1 }).setContent(String(f.properties.n)).setLatLng(layer.getBounds().getCenter()));
    });
    data.parcels.features.forEach((f) => {
      const p = f.properties;
      const layer = L.geoJSON(f, { renderer: canvas, style: () => styleFor(p) });
      layer.on('click', () => { if (stateAt(p, year).exists) select(p.id, false); });
      plots.set(p.id, { layer, props: p, ring: ringOf(f.geometry) });
      if (p.code) { (byCode.get(p.code) || byCode.set(p.code, []).get(p.code)).push(p.id); }
      groups.plots.addLayer(layer);
    });
    const list = $('vm-codes');
    [...byCode.keys()].sort().forEach((code) => { const o = document.createElement('option'); o.value = code; list.appendChild(o); });
    applyLayerBoxes();
    updateStats();
    updateLegend();
  }

  // ---------- layer boxes ----------
  function setGroup(group, on) { if (on && !map.hasLayer(group)) group.addTo(map); if (!on && map.hasLayer(group)) map.removeLayer(group); }
  function boxOn(name) { const el = document.querySelector(`[data-layer="${name}"]`); return Boolean(el && el.checked); }
  async function fetchLayer(url) { const r = await fetch(url, { credentials: 'same-origin' }); if (!r.ok) throw new Error(String(r.status)); return r.json(); }

  async function applyLayerBoxes() {
    setGroup(groups.plots, boxOn('plots'));
    setGroup(groups.blocks, boxOn('blocks'));
    setGroup(groups.zones, boxOn('zones'));
    setGroup(groups.blockLabels, boxOn('block-labels') && map.getZoom() >= 16);
    if (boxOn('buildings')) {
      if (!buildingsLoaded) {
        buildingsLoaded = true;
        try {
          const data = await fetchLayer(cfg.urls.buildings);
          data.features.forEach((feature) => {
            const parcelId = feature.properties.p;
            const layer = L.geoJSON(feature, { renderer: canvas, style: BUILDING_STYLE });
            layer.on('click', () => { if (parcelId && plots.has(parcelId)) select(parcelId, false, 'building'); });
            if (parcelId) { (buildingsOf.get(parcelId) || buildingsOf.set(parcelId, []).get(parcelId)).push(layer); }
            groups.buildings.addLayer(layer);
          });
        } catch (e) { buildingsLoaded = false; notice('بارگذاری اعیان ممکن نشد.', true); }
      }
      setGroup(groups.buildings, true);
    } else { setGroup(groups.buildings, false); }
    await applyEasements();
  }

  async function applyEasements() {
    const boxes = [...document.querySelectorAll('[data-easement]')];
    const wanted = boxes.filter((b) => b.checked).map((b) => b.dataset.easement);
    if (wanted.length && !easementsLoaded) {
      easementsLoaded = true;
      try {
        const data = await fetchLayer(cfg.urls.easements);
        Object.keys(cfg.easementKinds).forEach((kind) => {
          const color = EASEMENT_COLORS[kind];
          easementGroups[kind] = L.geoJSON({ type: 'FeatureCollection', features: data.features.filter((f) => f.properties.k === kind) }, {
            renderer: canvas, interactive: false,
            style: (f) => (f.geometry.type === 'LineString' ? { color, weight: 2.5, dashArray: '8 5', opacity: 0.95 } : { color, weight: 1.5, fillColor: color, fillOpacity: 0.28, opacity: 0.9 }),
          });
        });
      } catch (e) { easementsLoaded = false; notice('بارگذاری حریم‌ها ممکن نشد.', true); return; }
    }
    Object.entries(easementGroups).forEach(([kind, layer]) => setGroup(layer, wanted.includes(kind)));
    const all = $('vm-easements-all');
    all.checked = boxes.every((b) => b.checked);
    all.indeterminate = !all.checked && boxes.some((b) => b.checked);
  }

  document.querySelectorAll('[data-layer]').forEach((b) => b.addEventListener('change', applyLayerBoxes));
  document.querySelectorAll('[data-easement]').forEach((b) => b.addEventListener('change', applyEasements));
  $('vm-easements-all').addEventListener('change', (e) => {
    document.querySelectorAll('[data-easement]').forEach((b) => { b.checked = e.target.checked; });
    applyEasements();
  });
  document.querySelectorAll('input[name=colormode]').forEach((r) => r.addEventListener('change', () => { colorMode = r.value; restyleAll(); }));
  $('vm-layers-head').addEventListener('click', () => {
    const open = $('vm-layers').classList.toggle('is-open');
    $('vm-layers-head').setAttribute('aria-expanded', String(open));
  });
  $('vm-layers-toggle').addEventListener('click', () => $('vm-layers').classList.toggle('is-open'));

  // plot numbers only when zoomed in, so the map stays readable
  function updateLabels() {
    const zoom = map.getZoom();
    setGroup(groups.blockLabels, boxOn('block-labels') && zoom >= 16);
    if (zoom >= 19) {
      groups.plotLabels.clearLayers();
      const view = map.getBounds().pad(0.2);
      plots.forEach(({ layer, props }) => {
        if (!props.n || !stateAt(props, year).exists) return;
        const centre = layer.getBounds().getCenter();
        if (view.contains(centre)) groups.plotLabels.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'vm-plot-label', opacity: 1 }).setContent(props.n).setLatLng(centre));
      });
      setGroup(groups.plotLabels, true);
    } else { setGroup(groups.plotLabels, false); }
  }
  map.on('zoomend', updateLabels);
  map.on('moveend', () => { if (map.getZoom() >= 19) { map.removeLayer(groups.plotLabels); updateLabels(); } });

  // ---------- legend ----------
  function updateLegend() {
    const box = $('vm-legend');
    box.replaceChildren();
    const add = (color, text, style) => {
      const span = document.createElement('span');
      const sw = document.createElement('i'); sw.className = 'vm-sw'; sw.style.background = color; if (style) sw.style.borderStyle = style;
      span.append(sw, document.createTextNode(text));
      box.appendChild(span);
    };
    if (colorMode === 'status') { add(STATUS.empty.fillColor, 'بدون بایگانی'); add(STATUS.filed.fillColor, 'دارای بایگانی'); add(STATUS.paid.fillColor, 'دارای پرداخت'); add(STATUS.estimated.fillColor, 'مرز تقریبی', 'dashed'); }
    if (colorMode === 'zone') Object.entries(ZONE_COLORS).forEach(([n, c]) => add(c, `محله ${fa(n)}`));
    if (colorMode === 'easement') { add(EASEMENT_COLORS.qanat, 'در حریم'); add('#e5e7eb', 'خارج از حریم'); }
    if (colorMode === 'use') [...landUses.values()].slice(0, 14).forEach((u) => add(u.color, `${u.name} (${fa(u.count)})`));
    add('#c2410c', 'اعیان (ساختمان)');
    add('#fff', 'قفل‌شده: خط ضخیم قرمز', 'solid');
  }

  // ---------- timeline ----------
  const yearBox = $('vm-year');
  function setYear(value) {
    year = Number(value);
    yearBox.value = year;
    $('vm-year-out').textContent = year === LAST_YEAR ? `${faDigits(year)} (امسال)` : faDigits(year);
    restyleAll();
    if (map.getZoom() >= 19) updateLabels();
  }
  cfg.years.forEach((y) => { const s = document.createElement('span'); s.textContent = faDigits(y); $('vm-ticks').appendChild(s); });
  yearBox.addEventListener('input', () => setYear(yearBox.value));
  let timer = null;
  $('vm-play').addEventListener('click', () => {
    const icon = $('vm-play').querySelector('i');
    if (timer) { clearInterval(timer); timer = null; icon.className = 'fas fa-play'; return; }
    if (year >= LAST_YEAR) setYear(cfg.years[0]);
    icon.className = 'fas fa-pause';
    timer = setInterval(() => {
      if (year >= LAST_YEAR) { clearInterval(timer); timer = null; icon.className = 'fas fa-play'; return; }
      setYear(year + 1);
    }, 900);
  });

  // ---------- side panel ----------
  function openPanel() { $('vm-panel').classList.add('is-open'); $('vm-panel-toggle').setAttribute('aria-expanded', 'true'); }
  function closePanel() { $('vm-panel').classList.remove('is-open'); $('vm-panel-toggle').setAttribute('aria-expanded', 'false'); }
  $('vm-panel-toggle').addEventListener('click', () => ($('vm-panel').classList.contains('is-open') ? closePanel() : openPanel()));
  $('vm-close').addEventListener('click', () => { deselect(); closePanel(); });

  function deselect() {
    const old = selectedId;
    selectedId = null;
    if (old !== null) restyle(old);
    $('vm-parcel').hidden = true;
    $('vm-empty').hidden = false;
  }
  const parcelUrl = (id, suffix) => cfg.urls.parcel.replace(/0\/$/, `${id}/${suffix || ''}`);

  function showTab(name) {
    document.querySelectorAll('.vm-tab').forEach((t) => t.classList.toggle('is-on', t.dataset.tab === name));
    ['land', 'building', 'payments', 'locks'].forEach((pane) => { document.querySelector(`[data-pane="${pane}"]`).hidden = pane !== name; });
    $('vm-archive').querySelector('[data-pane-shared]').hidden = !['land', 'building'].includes(name);
  }

  async function select(id, zoom, focus) {
    const old = selectedId;
    selectedId = id;
    if (old !== null && old !== id) restyle(old);
    restyle(id);
    if (zoom) map.fitBounds(plots.get(id).layer.getBounds().pad(2), { maxZoom: 20 });
    openPanel();
    const response = await fetch(parcelUrl(id), { credentials: 'same-origin' });
    if (!response.ok) { show($('vm-archive-msg'), 'دریافت اطلاعات قطعه ممکن نشد.', true); return null; }
    const parcel = (await response.json()).parcel;
    fill(parcel);
    if (focus) showTab(focus);
    return parcel;
  }

  function fill(parcel) {
    $('vm-empty').hidden = true;
    $('vm-parcel').hidden = false;
    $('vm-parcel').dataset.id = parcel.id;
    $('vm-code').textContent = parcel.code || '— بدون کد —';
    $('vm-block').textContent = parcel.block || '—';
    $('vm-number').textContent = parcel.number || '—';
    $('vm-zone').textContent = parcel.zone ? `محله ${fa(parcel.zone)}` : '—';
    $('vm-lot').textContent = parcel.lot_no || '—';
    $('vm-area').textContent = `${fa(Math.round(parcel.area))} م²`;
    const floorArea = parcel.archive.building_floor_area;
    $('vm-building').textContent = parcel.building_count
      ? `${fa(Math.round(parcel.building_area))} م² سطح اشغال (${fa(parcel.building_count)} بنا)${floorArea ? `، زیربنا ${fa(Math.round(floorArea))} م²` : ''}${parcel.archive.building_floors ? `، ${fa(parcel.archive.building_floors)} طبقه` : ''}`
      : 'بدون بنا';
    $('vm-land-owner').textContent = parcel.archive.owner_name ? `مالک عرصه: ${parcel.archive.owner_name}` : 'مالک عرصه ثبت نشده';
    $('vm-building-owner').textContent = parcel.archive.building_owner_name ? `مالک اعیان: ${parcel.archive.building_owner_name}` : 'مالک اعیان ثبت نشده';
    $('vm-permit-mark').hidden = !parcel.permit_in_drawing;
    const use = $('vm-use');
    use.replaceChildren();
    if (parcel.land_use) {
      const dot = document.createElement('i'); dot.className = 'vm-sw'; dot.style.background = parcel.land_use.color;
      const known = [...landUses.values()].find((u) => u.color === parcel.land_use.color);
      use.append(dot, document.createTextNode(parcel.land_use.name || (known ? known.name : 'نام ثبت نشده')));
    } else { use.textContent = 'نامشخص'; }
    $('vm-estimated').hidden = parcel.kind !== 'estimated';
    $('vm-duplicate').hidden = !parcel.duplicate;

    const viol = $('vm-violation');
    viol.replaceChildren();
    viol.hidden = parcel.easements.length === 0;
    if (parcel.easements.length) {
      const title = document.createElement('strong'); title.textContent = 'رعایت نکردن حریم';
      const ul = document.createElement('ul');
      parcel.easements.forEach((e) => {
        const li = document.createElement('li');
        li.textContent = e.line ? `${e.label}: خط حریم از این قطعه عبور می‌کند` : `${e.label}: ${fa(Math.round(e.amount))} م² از قطعه در حریم است`;
        if (e.rule) { const rule = document.createElement('small'); rule.className = 'vm-rule'; rule.textContent = e.rule; li.appendChild(document.createElement('br')); li.appendChild(rule); }
        ul.appendChild(li);
      });
      viol.append(title, ul);
    }
    const active = parcel.locks.filter((l) => l.active);
    const lockBanner = $('vm-locked');
    lockBanner.hidden = active.length === 0;
    lockBanner.textContent = active.length ? `این ملک قفل است و از خدمات محروم شده: ${active.map((l) => l.reason_label).join('، ')}` : '';

    const form = $('vm-archive');
    for (const [key, value] of Object.entries(parcel.archive)) { if (form.elements[key]) form.elements[key].value = value; }
    $('vm-updated').textContent = parcel.archive.updated_at ? `آخرین ویرایش: ${parcel.archive.updated_at}` : 'هنوز اطلاعاتی ثبت نشده است.';
    renderPayments(parcel);
    renderLocks(parcel);
    syncPlot(parcel);
  }

  // the plot's colour follows what the server says now
  function syncPlot(parcel) {
    const item = plots.get(parcel.id);
    if (!item) return;
    const p = item.props;
    p.f = parcel.archive.updated_at ? 1 : 0;
    p.pay = parcel.payments.map((x) => (x.paid_on ? Number(x.paid_on.slice(0, 4)) : x.fiscal_year) || LAST_YEAR);
    p.lk = parcel.locks.map((l) => [Number(l.locked_at.slice(0, 4)), l.active ? 0 : Number(l.unlocked_at.slice(0, 4))]);
    p.py = parcel.archive.permit_date ? Number(parcel.archive.permit_date.slice(0, 4)) : null;
    restyle(parcel.id);
    updateStats();
  }

  function renderPayments(parcel) {
    const list = $('vm-pay-list');
    list.replaceChildren();
    parcel.payments.forEach((pay) => {
      const li = document.createElement('li');
      const title = document.createElement('span'); title.className = 'vm-amt';
      title.textContent = `${pay.fee_type} — ${fa(pay.amount)} ریال`;
      const meta = document.createElement('span'); meta.className = 'vm-meta';
      meta.textContent = [pay.fiscal_year && `سال ${pay.fiscal_year}`, pay.paid_on, pay.receipt_no && `فیش ${pay.receipt_no}`, pay.notes].filter(Boolean).join(' · ');
      li.append(title, meta);
      if (canEdit) {
        const del = document.createElement('button'); del.type = 'button'; del.textContent = 'حذف';
        del.addEventListener('click', () => deletePayment(pay.id));
        li.appendChild(del);
      }
      list.appendChild(li);
    });
    $('vm-pay-total').textContent = parcel.payments.length ? `جمع پرداخت‌ها: ${fa(parcel.payments_total)} ریال` : 'هنوز پرداختی ثبت نشده است.';
    $('vm-pay-count').textContent = parcel.payments.length ? fa(parcel.payments.length) : '';
  }

  function renderLocks(parcel) {
    const list = $('vm-lock-list');
    list.replaceChildren();
    if (!parcel.locks.length) { const li = document.createElement('li'); li.textContent = 'این ملک تا کنون قفل نشده است.'; list.appendChild(li); }
    parcel.locks.forEach((lock) => {
      const li = document.createElement('li');
      li.classList.toggle('is-active', lock.active);
      const title = document.createElement('span'); title.className = 'vm-amt';
      title.textContent = `${lock.reason_label}${lock.active ? ' — فعال' : ' — رفع شده'}`;
      const meta = document.createElement('span'); meta.className = 'vm-meta';
      meta.textContent = [`از ${lock.locked_at}`, lock.locked_by && `توسط ${lock.locked_by}`, lock.notes, lock.unlocked_at && `رفع قفل ${lock.unlocked_at}: ${lock.unlock_notes}`].filter(Boolean).join(' · ');
      li.append(title, meta);
      if (canLock && lock.active) {
        const btn = document.createElement('button'); btn.type = 'button'; btn.textContent = 'رفع قفل';
        btn.addEventListener('click', () => releaseLock(lock.id));
        li.appendChild(btn);
      }
      list.appendChild(li);
    });
    const n = parcel.locks.filter((l) => l.active).length;
    $('vm-lock-count').textContent = n ? fa(n) : '';
  }

  function show(el, text, isError) { el.textContent = text; el.className = `vm-msg ${text ? (isError ? 'is-error' : 'is-ok') : ''}`; }
  function notice(text, isError) {
    const el = $('vm-notice');
    el.textContent = text; el.hidden = !text; el.classList.toggle('is-error', Boolean(isError));
    clearTimeout(notice.t);
    if (text) notice.t = setTimeout(() => { el.hidden = true; }, 9000);
  }

  async function post(url, body) {
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cfg.csrf }, body: JSON.stringify(body || {}) });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok && data.success, data };
  }
  const currentId = () => $('vm-parcel').dataset.id;
  const submitterOf = (event) => event.submitter || event.target.querySelector('button[type=submit]');

  $('vm-archive').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const button = submitterOf(event); button.disabled = true;
    const { ok, data } = await post(parcelUrl(currentId(), 'archive/'), Object.fromEntries(new FormData(event.target).entries()));
    button.disabled = false;
    show($('vm-archive-msg'), ok ? 'ذخیره شد.' : (data.error || 'ذخیره انجام نشد.'), !ok);
    if (ok) fill(data.parcel);
  });
  $('vm-pay-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const button = submitterOf(event); button.disabled = true;
    const { ok, data } = await post(parcelUrl(currentId(), 'payments/'), Object.fromEntries(new FormData(event.target).entries()));
    button.disabled = false;
    show($('vm-pay-msg'), ok ? 'پرداخت ثبت شد.' : (data.error || 'ثبت انجام نشد.'), !ok);
    if (ok) { event.target.reset(); fill(data.parcel); }
  });
  async function deletePayment(id) {
    if (!confirm('این پرداخت حذف شود؟')) return;
    const { ok, data } = await post(parcelUrl(currentId(), `payments/${id}/delete/`));
    if (ok) fill(data.parcel); else show($('vm-pay-msg'), data.error || 'حذف انجام نشد.', true);
  }
  $('vm-lock-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!canLock) return;
    if (!confirm('این ملک قفل شود و از خدمات محروم گردد؟')) return;
    const button = submitterOf(event); button.disabled = true;
    const { ok, data } = await post(parcelUrl(currentId(), 'lock/'), Object.fromEntries(new FormData(event.target).entries()));
    button.disabled = false;
    show($('vm-lock-msg'), ok ? 'ملک قفل شد.' : (data.error || 'قفل انجام نشد.'), !ok);
    if (ok) { event.target.reset(); fill(data.parcel); }
  });
  async function releaseLock(id) {
    const notes = prompt('دلیل رفع قفل را بنویسید:');
    if (!notes) return;
    const { ok, data } = await post(parcelUrl(currentId(), `locks/${id}/release/`), { notes });
    if (ok) fill(data.parcel); else show($('vm-lock-msg'), data.error || 'رفع قفل انجام نشد.', true);
  }

  document.querySelectorAll('.vm-tab').forEach((tab) => tab.addEventListener('click', () => {
    showTab(tab.dataset.tab);
  }));
  $('vm-filter').addEventListener('change', () => { filter = $('vm-filter').value; restyleAll(); });

  // ---------- search: code, block, UTM "X Y", or "lat, lng" ----------
  function containing(lat, lng) {
    for (const [id, { ring, props }] of plots) {
      if (!stateAt(props, year).exists) continue;
      let inside = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [yi, xi] = ring[i], [yj, xj] = ring[j];
        if (((yi > lat) !== (yj > lat)) && (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
      }
      if (inside) return id;
    }
    return null;
  }
  let pin = null;
  async function goTo(lat, lng, label) {
    if (pin) map.removeLayer(pin);
    pin = L.circleMarker([lat, lng], { radius: 9, color: '#dc2626', weight: 3, fillColor: '#fecaca', fillOpacity: 0.7 }).addTo(map);
    map.setView([lat, lng], Math.max(map.getZoom(), 19));
    const id = containing(lat, lng);
    if (id) { announce(await select(id, false)); } else { notice(`${label}: داخل هیچ قطعه‌ای نیست.`); }
  }
  function announce(parcel) {
    if (!parcel) return;
    const bits = [parcel.code || 'قطعه بدون کد'];
    if (parcel.easements.length) bits.push(`حریم رعایت نشده: ${parcel.easements.map((e) => e.label).join('، ')}`);
    if (parcel.locked) bits.push('قفل است و از خدمات محروم شده');
    notice(bits.join(' — '), parcel.easements.length > 0 || parcel.locked);
  }

  $('vm-search').addEventListener('submit', async (event) => {
    event.preventDefault();
    const raw = toDigits($('vm-search-input').value).trim();
    if (!raw) return;
    const nums = raw.match(/-?\d+(?:\.\d+)?/g) || [];
    const coordinateLike = /^[\d\s.,;:xXyY=]+$/.test(raw);
    if (coordinateLike && nums.length === 2) {
      const [a, b] = nums.map(Number);
      if (a > 100000 && b > 1000000) { const [lat, lng] = UTM.toLatLng(a, b); return goTo(lat, lng, `X ${a}، Y ${b}`); }
      if (b > 100000 && a > 1000000) { const [lat, lng] = UTM.toLatLng(b, a); return goTo(lat, lng, `X ${b}، Y ${a}`); }
      if (a > 20 && a < 45 && b > 40 && b < 70) return goTo(a, b, `${a}, ${b}`);
      if (b > 20 && b < 45 && a > 40 && a < 70) return goTo(b, a, `${b}, ${a}`);
    }
    const lotMatch = raw.match(/^(?:t|lot|ت|تفکیکی)\s*[-:]?\s*(\d+)$/i);
    if (lotMatch) {
      const hit = [...plots.entries()].find(([, { props }]) => props.lt === lotMatch[1]);
      if (hit) { announce(await select(hit[0], true)); return; }
    }
    const text = raw.replace(/[\s_/\\]+/g, '-');
    let ids = byCode.get(text);
    if (!ids) {                                   // partial codes: "ملک-بلوک-محله" or "ملک-بلوک" (either order)
      const parts = text.split('-');
      const hit = [];
      plots.forEach(({ props }, id) => {
        if (parts.length === 3 && props.n === parts[0] && props.b === parts[1] && props.z === parts[2]) hit.push(id);
        else if (parts.length === 2 && ((props.n === parts[0] && props.b === parts[1]) || (props.b === parts[0] && props.n === parts[1]))) hit.push(id);
      });
      ids = hit.length ? hit : null;
    }
    if (ids) {
      const parcel = await select(ids[0], true);
      announce(parcel);
      if (ids.length > 1) notice(`${fa(ids.length)} قطعه با این شماره پیدا شد؛ اولی نشان داده شد. کد کامل را بنویسید.`);
      return;
    }
    const block = blockLayers.get(text);
    if (block) { map.fitBounds(block.getBounds().pad(0.1)); return; }
    $('vm-search-input').setCustomValidity('پیدا نشد');
    $('vm-search-input').reportValidity();
    setTimeout(() => $('vm-search-input').setCustomValidity(''), 1500);
  });

  map.on('mousemove', (e) => {
    const [x, y] = UTM.fromLatLng(e.latlng.lat, e.latlng.lng);
    $('vm-coords').textContent = `X ${Math.round(x)}  Y ${Math.round(y)}  |  ${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
  });

  // ---------- start ----------
  if (window.matchMedia('(max-width: 767.98px)').matches) $('vm-layers').classList.remove('is-open');   // phones: layers open on demand
  setYear(LAST_YEAR);
  fetchLayer(cfg.urls.data)
    .then((data) => {
      render(data);
      const all = L.featureGroup([...plots.values()].map((p) => p.layer));
      map.invalidateSize();
      const fit = () => map.fitBounds(all.getBounds().pad(0.05));
      if (map.getSize().x > 0) fit(); else fitToVillage = fit;
      $('vm-loading').hidden = true;
      updateLabels();
    })
    .catch(() => { $('vm-loading').textContent = 'بارگذاری نقشه ممکن نشد. صفحه را دوباره باز کنید.'; });

  // a page opened in a background tab has no size yet: fit the village the first time it gets one
  new ResizeObserver(() => {
    map.invalidateSize();
    if (fitToVillage && map.getSize().x > 0) { const fit = fitToVillage; fitToVillage = null; fit(); }
  }).observe($('vm-map'));
})();
