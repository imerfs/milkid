/* The citizen's property inquiry map: plots coloured by land use, outlined when inside the plan or exempt, plot numbers and street names on the map,
   search by renewal code / plot number, one card per plot (no private data). The street map is drawn from the village's own drawing (no tile server);
   the satellite picture is served by this site. */
(function () {
    'use strict';
    var config = JSON.parse(document.getElementById('pi-config').textContent);
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }
    function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    var map = L.map('pi-map', { zoomControl: true, preferCanvas: true, maxZoom: 21, minZoom: 12, zoomSnap: 0.5, attributionControl: true });
    map.attributionControl.setPrefix(false);
    var canvas = L.canvas({ padding: 0.5 });
    var layer = null, byId = {}, uses = {}, selected = null, filter = 'all', useFilter = null, satellite = null, base = 'street';
    var labels = L.layerGroup(), streetLabels = L.layerGroup(), context = L.layerGroup().addTo(map);

    if (config.satellite) {
        satellite = L.tileLayer(config.satellite.url, { maxZoom: 21, maxNativeZoom: config.satellite.nativeZoom || 18, attribution: config.satellite.attribution || '' });
    }

    var RING = { exempt: ['#16a34a', 3], plan: ['#ea580c', 2.6] };
    function kind(p) { return p.x ? 'exempt' : (p.p ? 'plan' : 'plain'); }
    function visible(p) {
        if (useFilter !== null && p.l !== useFilter) return false;
        if (filter === 'plan') return !!p.p;
        if (filter === 'exempt') return !!p.x;
        if (filter === 'clear') return !p.p && !p.x;
        return true;
    }
    function fill(p) { return (uses[p.l] || {}).color || '#d1d5db'; }
    function style(feature) {
        var p = feature.properties, on = visible(p), me = selected === feature.id, sat = base === 'satellite', ring = RING[kind(p)];
        var s = { renderer: canvas, fillColor: fill(p), fillOpacity: on ? (sat ? 0.32 : 0.62) : 0.05, color: sat ? '#f8fafc' : '#ffffff', weight: sat ? 0.9 : 0.7, opacity: on ? 0.9 : 0.25, dashArray: p.e ? '4 3' : null };
        if (ring && on) { s.color = ring[0]; s.weight = ring[1]; s.opacity = 1; }
        if (me) { s.color = '#0f172a'; s.weight = 3.2; s.opacity = 1; s.fillOpacity = 0.85; }
        return s;
    }
    function restyle() { if (layer) layer.setStyle(style); drawLabels(); }

    // ---------- plot numbers and street names ----------
    function drawLabels() {
        labels.clearLayers();
        if (!layer || map.getZoom() < 18) { if (map.hasLayer(labels)) map.removeLayer(labels); return; }
        var view = map.getBounds().pad(0.1), n = 0, sat = base === 'satellite';
        layer.eachLayer(function (lyr) {
            var p = lyr.feature.properties;
            if (!p.n || !visible(p) || n > 900) return;
            var b = lyr.getBounds();
            if (!view.intersects(b)) return;
            var a = map.latLngToContainerPoint(b.getNorthWest()), c = map.latLngToContainerPoint(b.getSouthEast());
            if (Math.abs(c.x - a.x) < 16 || Math.abs(c.y - a.y) < 11) return;          // too small to hold a number
            n++;
            labels.addLayer(L.tooltip({ permanent: true, direction: 'center', className: 'pi-plot' + (sat ? ' is-sat' : ''), opacity: 1, interactive: false }).setContent(esc(fa(p.n))).setLatLng(b.getCenter()));
        });
        if (!map.hasLayer(labels)) labels.addTo(map);
    }
    function drawStreets(data) {
        (data.streets || []).forEach(function (s) {
            var el = document.createElement('span');
            el.className = 'pi-street';
            el.textContent = s.t.replace(/^\d+/, function (d) { return fa(d) + ' '; });
            el.style.transform = 'rotate(' + (-(s.r || 0)) + 'deg)';
            streetLabels.addLayer(L.marker([s.y, s.x], { interactive: false, keyboard: false, icon: L.divIcon({ className: 'pi-street-wrap', html: el.outerHTML, iconSize: [0, 0] }) }));
        });
        syncStreets();
    }
    function syncStreets() {
        var on = map.getZoom() >= 16;
        if (on && !map.hasLayer(streetLabels)) streetLabels.addTo(map);
        if (!on && map.hasLayer(streetLabels)) map.removeLayer(streetLabels);
    }
    map.on('zoomend', function () { syncStreets(); drawLabels(); });
    map.on('moveend', drawLabels);

    // ---------- street map or satellite ----------
    function setBase(name) {
        base = name;
        document.getElementById('pi-map').classList.toggle('is-sat', name === 'satellite');
        if (satellite) { if (name === 'satellite') { satellite.addTo(map); satellite.bringToBack(); } else { map.removeLayer(satellite); } }
        document.querySelectorAll('.pi-base-btn').forEach(function (b) { b.classList.toggle('is-on', b.getAttribute('data-base') === name); });
        restyle();
    }
    document.querySelectorAll('.pi-base-btn').forEach(function (b) { b.addEventListener('click', function () { setBase(b.getAttribute('data-base')); }); });

    // ---------- card ----------
    function show(el) { ['pi-hint', 'pi-results', 'pi-card'].forEach(function (id) { document.getElementById(id).hidden = id !== el; }); }
    function icon(state) { return '<svg class="pi-svg"><use href="#' + (state === 'ok' ? 'i-ok' : 'i-alert') + '"/></svg>'; }
    function renderCard(c) {
        var fact = function (label, value) { return '<div><dt>' + label + '</dt><dd>' + (value ? esc(fa(value)) : '—') + '</dd></div>'; };
        var rows = c.status.map(function (s) { return '<li class="is-' + s.state + '">' + icon(s.state) + '<span>' + esc(fa(s.text)) + '</span></li>'; }).join('');
        var use = '<div class="pi-use"><dt>کاربری</dt><dd>' + (c.land_use_color ? '<i class="pi-sw" style="background:' + esc(c.land_use_color) + '"></i>' : '') + esc(fa(c.land_use || '—')) + '</dd></div>';
        var el = document.getElementById('pi-card');
        el.innerHTML = '<h2>قطعه‌ی شماره‌ی ' + esc(fa(c.number || 'بدون شماره')) + '</h2><span class="pi-code">' + esc(fa(c.code || '')) + '</span>' +
            '<dl class="pi-facts">' + fact('بلوک', c.block) + fact('محله', c.zone_name) + fact('مساحت (مترمربع)', c.area) + fact('شماره‌ی قطعه', c.number) + use + '</dl>' +
            '<ul class="pi-status">' + rows + '</ul><p class="pi-notice">' + esc(c.notice) + '</p>' +
            '<button type="button" class="pi-back" id="pi-clear">بازگشت</button>';
        show('pi-card');
        document.getElementById('pi-clear').addEventListener('click', function () { select(null); show('pi-hint'); });
    }
    function select(id, fly) {
        selected = id;
        restyle();
        if (id == null) return;
        var feature = byId[id];
        if (feature) { if (fly) map.fitBounds(feature.getBounds(), { maxZoom: 20, padding: [60, 60] }); feature.bringToFront(); }
        fetch(config.urls.parcel.replace(/0\/$/, id + '/'), { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) { renderCard(d.parcel); });
    }

    // ---------- chips and legend ----------
    function counts(features) {
        var n = { all: features.length, plan: 0, exempt: 0, clear: 0 };
        features.forEach(function (f) { var p = f.properties; if (p.p) n.plan++; if (p.x) n.exempt++; if (!p.p && !p.x) n.clear++; });
        Object.keys(n).forEach(function (k) { document.getElementById('pi-n-' + k).textContent = fa(n[k]); });
    }
    function legend(data) {
        var box = document.getElementById('pi-uses');
        var total = {};
        data.features.forEach(function (f) { total[f.properties.l] = (total[f.properties.l] || 0) + 1; });
        box.innerHTML = (data.land_uses || []).filter(function (u) { return total[u.id]; }).map(function (u) {
            return '<li><button type="button" class="pi-use-btn" data-use="' + u.id + '"><i class="pi-sw" style="background:' + esc(u.color) + '"></i><span>' + esc(fa(u.name)) + '</span><b>' + fa(total[u.id]) + '</b></button></li>';
        }).join('');
        box.querySelectorAll('.pi-use-btn').forEach(function (b) {
            b.addEventListener('click', function () {
                var id = +b.getAttribute('data-use');
                useFilter = useFilter === id ? null : id;                         // a second click shows every land use again
                box.querySelectorAll('.pi-use-btn').forEach(function (o) { o.classList.toggle('is-on', useFilter !== null && +o.getAttribute('data-use') === useFilter); });
                restyle();
            });
        });
    }

    fetch(config.urls.data, { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (data) {
        (data.land_uses || []).forEach(function (u) { uses[u.id] = u; });
        if (data.limit) L.geoJSON(data.limit, { renderer: canvas, interactive: false, style: { color: '#ca8a04', weight: 2, fill: false, dashArray: '10 6', opacity: 0.9 } }).addTo(context);
        if (data.roads && data.roads.length) L.geoJSON({ type: 'FeatureCollection', features: data.roads }, { renderer: canvas, interactive: false, style: { color: '#ffffff', weight: 4, opacity: 0.95 } }).addTo(context);
        layer = L.geoJSON(data, {
            style: style,
            onEachFeature: function (feature, lyr) {
                byId[feature.id] = lyr;
                lyr.on('click', function () { select(feature.id, false); });
            }
        }).addTo(map);
        map.fitBounds(layer.getBounds(), { padding: [20, 20] });
        counts(data.features);
        legend(data);
        drawStreets(data);
        drawLabels();
        document.getElementById('pi-loading').hidden = true;
    }).catch(function () { document.getElementById('pi-loading').textContent = 'بارگذاری نقشه انجام نشد؛ صفحه را دوباره باز کنید.'; });

    document.querySelectorAll('.pi-chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            filter = chip.getAttribute('data-filter');
            document.querySelectorAll('.pi-chip').forEach(function (c) { c.classList.toggle('is-on', c === chip); });
            restyle();
        });
    });

    // ---------- search ----------
    document.getElementById('pi-search').addEventListener('submit', function (e) {
        e.preventDefault();
        var q = document.getElementById('pi-q').value.trim();
        if (!q) return;
        fetch(config.urls.search + '?q=' + encodeURIComponent(q), { credentials: 'same-origin' }).then(function (r) {
            if (r.status === 429) throw new Error('limit');
            return r.json();
        }).then(function (d) {
            var list = document.getElementById('pi-results');
            if (!d.results.length) { list.innerHTML = '<li class="pi-hint">ملکی با این مشخصات پیدا نشد. کد نوسازی را به شکل ۰-۰-۱۲-۶۹-۳ یا شماره‌ی قطعه را وارد کنید.</li>'; show('pi-results'); return; }
            if (d.results.length === 1) { select(d.results[0].id, true); return; }
            list.innerHTML = d.results.map(function (c) {
                return '<li><button type="button" data-id="' + c.id + '">قطعه ' + esc(fa(c.number)) + ' · بلوک ' + esc(fa(c.block)) + '<small>' + esc(fa(c.code)) + ' · ' + esc(fa(c.land_use || '')) + '</small></button></li>';
            }).join('');
            show('pi-results');
            list.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { select(+b.getAttribute('data-id'), true); }); });
        }).catch(function (err) {
            var list = document.getElementById('pi-results');
            list.innerHTML = '<li class="pi-hint">' + (err.message === 'limit' ? 'تعداد جستجوها زیاد بود؛ کمی بعد دوباره تلاش کنید.' : 'جستجو انجام نشد.') + '</li>';
            show('pi-results');
        });
    });
}());
