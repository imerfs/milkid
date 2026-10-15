/* Village web-GIS: draws the blocks and plots on a Leaflet map and runs the plot archive side panel.
   All text from the server goes in with textContent / input.value, never as HTML. */
(function () {
  'use strict';

  const app = document.getElementById('vm-app');
  const $ = (id) => document.getElementById(id);
  const canEdit = app.dataset.canEdit === '1';
  const csrf = app.dataset.csrf;
  if (!canEdit) app.classList.add('vm-readonly');

  const STYLE = {
    empty: { fillColor: '#cbd5e1', color: '#475569' },
    filed: { fillColor: '#86efac', color: '#166534' },
    paid: { fillColor: '#60a5fa', color: '#1e3a8a' },
    estimated: { fillColor: '#fca5a5', color: '#7f1d1d' },
  };
  const toDigits = (s) => String(s).replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
  const fa = (n) => Number(n).toLocaleString('fa-IR');

  const map = L.map('vm-map', { preferCanvas: true, zoomControl: true, minZoom: 13, maxZoom: 21, zoomSnap: 0.5, attributionControl: false });
  const canvas = L.canvas({ padding: 0.5 });
  window.villageMap = map;      // handy in the browser console when checking a deployment
  let tiles = null;
  $('vm-basemap').addEventListener('change', (event) => {
    if (event.target.checked) {
      tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
      tiles.bringToBack();
    } else if (tiles) { map.removeLayer(tiles); tiles = null; }
  });

  const plots = new Map();        // id -> { layer, props }
  const byCode = new Map();       // code -> [id]
  const blockLayers = new Map();  // block number -> layer
  let filter = 'all';
  let fitToVillage = null;
  let blockCount = 0;
  let selectedId = null;
  let plotLabels = L.layerGroup();
  const blockLabels = L.layerGroup();
  map.setView([0, 0], 15);      // Leaflet needs a view before layers are added; the real one is set when the data is in

  function plotStatus(p) {
    if (p.e) return 'estimated';
    if (p.p) return 'paid';
    if (p.f) return 'filed';
    return 'empty';
  }
  function styleFor(p) {
    const base = STYLE[plotStatus(p)];
    const visible = filter === 'all' || (filter === 'filed' && (p.f || p.p)) || (filter === 'empty' && !(p.f || p.p) && !p.e) || (filter === 'estimated' && p.e);
    return { ...base, weight: 1, dashArray: p.e ? '4 3' : null, fillOpacity: visible ? 0.75 : 0.08, opacity: visible ? 1 : 0.25 };
  }
  function restyle(id) {
    const item = plots.get(id);
    if (!item) return;
    item.layer.setStyle(id === selectedId ? { color: '#d97706', weight: 3, fillColor: '#fbbf24', fillOpacity: 0.9, dashArray: null } : styleFor(item.props));
    if (id === selectedId) item.layer.bringToFront();
  }

  function updateStats() {
    let estimated = 0, filed = 0;
    plots.forEach(({ props }) => { if (props.e) estimated += 1; if (props.f || props.p) filed += 1; });
    $('vm-stats').textContent = `${fa(blockCount)} بلوک · ${fa(plots.size)} قطعه (${fa(plots.size - estimated)} ترسیم‌شده، ${fa(estimated)} تقریبی) · ${fa(filed)} قطعه دارای بایگانی`;
  }

  function render(collection) {
    const codes = [];
    let blocks = 0;
    for (const feature of collection.features) {
      const p = feature.properties;
      if (p.t === 'b') {
        blocks += 1;
        const layer = L.geoJSON(feature, { renderer: canvas, interactive: false, style: { color: '#1e40af', weight: 2, fill: false } }).addTo(map);
        blockLayers.set(p.n, layer);
        const centre = layer.getBounds().getCenter();
        blockLabels.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'vm-block-label', opacity: 1 }).setContent(String(p.n)).setLatLng(centre));
        continue;
      }
      const layer = L.geoJSON(feature, { renderer: canvas, style: () => styleFor(p) }).addTo(map);
      layer.on('click', () => select(p.id, false));
      plots.set(p.id, { layer, props: p });
      if (p.code) { codes.push(p.code); (byCode.get(p.code) || byCode.set(p.code, []).get(p.code)).push(p.id); }
    }
    blockCount = blocks;
    updateStats();
    const list = $('vm-codes');
    [...new Set(codes)].sort().forEach((code) => { const o = document.createElement('option'); o.value = code; list.appendChild(o); });
  }

  // plot numbers appear only when zoomed in, so the map stays readable
  function updateLabels() {
    const zoom = map.getZoom();
    if (zoom >= 16 && !map.hasLayer(blockLabels)) blockLabels.addTo(map);
    else if (zoom < 16 && map.hasLayer(blockLabels)) map.removeLayer(blockLabels);
    if (zoom >= 19 && !map.hasLayer(plotLabels)) {
      plotLabels.clearLayers();
      const view = map.getBounds().pad(0.2);
      plots.forEach(({ layer, props }) => {
        if (!props.n) return;
        const centre = layer.getBounds().getCenter();
        if (view.contains(centre)) plotLabels.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'vm-plot-label', opacity: 1 }).setContent(props.n).setLatLng(centre));
      });
      plotLabels.addTo(map);
    } else if (zoom < 19 && map.hasLayer(plotLabels)) {
      map.removeLayer(plotLabels);
    }
  }
  map.on('zoomend', updateLabels);
  map.on('moveend', () => { if (map.hasLayer(plotLabels)) { map.removeLayer(plotLabels); updateLabels(); } });

  // ---- side panel ----
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

  async function select(id, zoom) {
    const old = selectedId;
    selectedId = id;
    if (old !== null && old !== id) restyle(old);
    restyle(id);
    if (zoom) map.fitBounds(plots.get(id).layer.getBounds().pad(2), { maxZoom: 20 });
    openPanel();
    const response = await fetch(app.dataset.parcelUrl.replace(/0\/$/, `${id}/`), { credentials: 'same-origin' });
    if (!response.ok) { showMessage($('vm-archive-msg'), 'دریافت اطلاعات قطعه ممکن نشد.', true); return; }
    fill((await response.json()).parcel);
  }

  function fill(parcel) {
    $('vm-empty').hidden = true;
    $('vm-parcel').hidden = false;
    $('vm-parcel').dataset.id = parcel.id;
    $('vm-code').textContent = parcel.code || '— بدون کد —';
    $('vm-block').textContent = parcel.block || '—';
    $('vm-number').textContent = parcel.number || '—';
    $('vm-area').textContent = `${fa(Math.round(parcel.area))} م²`;
    $('vm-estimated').hidden = parcel.kind !== 'estimated';
    $('vm-duplicate').hidden = !parcel.duplicate;
    const form = $('vm-archive');
    for (const [key, value] of Object.entries(parcel.archive)) { if (form.elements[key]) form.elements[key].value = value; }
    $('vm-updated').textContent = parcel.archive.updated_at ? `آخرین ویرایش: ${parcel.archive.updated_at}` : 'هنوز اطلاعاتی ثبت نشده است.';
    renderPayments(parcel);
    const item = plots.get(parcel.id);
    if (item) { item.props.f = Boolean(parcel.archive.updated_at); item.props.p = parcel.payments.length > 0; restyle(parcel.id); updateStats(); }
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

  function showMessage(el, text, isError) {
    el.textContent = text;
    el.className = `vm-msg ${text ? (isError ? 'is-error' : 'is-ok') : ''}`;
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok && data.success, data };
  }
  const parcelUrl = (suffix) => app.dataset.parcelUrl.replace(/0\/$/, `${$('vm-parcel').dataset.id}/${suffix}`);

  $('vm-archive').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const button = event.submitter || event.target.querySelector('button[type=submit]'); button.disabled = true;
    const body = Object.fromEntries(new FormData(event.target).entries());
    const { ok, data } = await post(parcelUrl('archive/'), body);
    button.disabled = false;
    showMessage($('vm-archive-msg'), ok ? 'ذخیره شد.' : (data.error || 'ذخیره انجام نشد.'), !ok);
    if (ok) fill(data.parcel);
  });

  $('vm-pay-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!canEdit) return;
    const button = event.submitter || event.target.querySelector('button[type=submit]'); button.disabled = true;
    const body = Object.fromEntries(new FormData(event.target).entries());
    const { ok, data } = await post(parcelUrl('payments/'), body);
    button.disabled = false;
    showMessage($('vm-pay-msg'), ok ? 'پرداخت ثبت شد.' : (data.error || 'ثبت انجام نشد.'), !ok);
    if (ok) { event.target.reset(); fill(data.parcel); }
  });

  async function deletePayment(id) {
    if (!confirm('این پرداخت حذف شود؟')) return;
    const { ok, data } = await post(parcelUrl(`payments/${id}/delete/`));
    if (ok) fill(data.parcel); else showMessage($('vm-pay-msg'), data.error || 'حذف انجام نشد.', true);
  }

  document.querySelectorAll('.vm-tab').forEach((tab) => tab.addEventListener('click', () => {
    document.querySelectorAll('.vm-tab').forEach((t) => t.classList.toggle('is-on', t === tab));
    $('vm-archive').hidden = tab.dataset.tab !== 'archive';
    $('vm-payments').hidden = tab.dataset.tab !== 'payments';
  }));

  document.querySelectorAll('.vm-chip').forEach((chip) => chip.addEventListener('click', () => {
    filter = chip.dataset.filter;
    document.querySelectorAll('.vm-chip').forEach((c) => c.classList.toggle('is-on', c === chip));
    plots.forEach((_, id) => restyle(id));
  }));

  // ---- search: "69-12" selects the plot, "69" flies to the block ----
  $('vm-search').addEventListener('submit', (event) => {
    event.preventDefault();
    const text = toDigits($('vm-search-input').value).trim().replace(/[\s_/\\]+/g, '-');
    if (!text) return;
    const ids = byCode.get(text);
    if (ids) { select(ids[0], true); return; }
    const block = blockLayers.get(text);
    if (block) { map.fitBounds(block.getBounds().pad(0.1)); return; }
    $('vm-search-input').setCustomValidity('پیدا نشد');
    $('vm-search-input').reportValidity();
    setTimeout(() => $('vm-search-input').setCustomValidity(''), 1500);
  });

  // ---- start ----
  fetch(app.dataset.dataUrl, { credentials: 'same-origin' })
    .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
    .then((collection) => {
      render(collection);
      const all = L.featureGroup([...plots.values()].map((p) => p.layer));
      fitToVillage = () => map.fitBounds(all.getBounds().pad(0.05));
      map.invalidateSize();
      if (map.getSize().x > 0) { fitToVillage(); fitToVillage = null; }   // else: the page is hidden; fit when it is shown
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
