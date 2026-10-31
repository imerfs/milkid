/* The citizen's property inquiry map: plots coloured by status, search by renewal code / plot number, one card per plot (no private data). */
(function () {
    'use strict';
    var config = JSON.parse(document.getElementById('pi-config').textContent);
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    function fa(t) { return String(t == null ? '' : t).replace(/\d/g, function (d) { return FA[d]; }); }
    function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    var map = L.map('pi-map', { zoomControl: true, preferCanvas: true, maxZoom: 21, minZoom: 12, attributionControl: true });
    var layer = null, byId = {}, selected = null, filter = 'all';
    var basemap = config.basemap;
    if (basemap) {
        L.tileLayer(basemap.url, { maxZoom: 21, maxNativeZoom: basemap.nativeZoom || 19, subdomains: basemap.subdomains || 'abc', attribution: basemap.attribution || '' }).addTo(map);
    }

    var COLOURS = { plain: ['#2563eb', '#3b82f6'], plan: ['#d97706', '#f59e0b'], exempt: ['#16a34a', '#39ff14'] };       // outline, fill
    function kind(p) { return p.x ? 'exempt' : (p.p ? 'plan' : 'plain'); }
    function visible(p) {
        if (filter === 'plan') return !!p.p;
        if (filter === 'exempt') return !!p.x;
        if (filter === 'clear') return !p.p && !p.x;
        return true;
    }
    function style(feature) {
        var p = feature.properties, c = COLOURS[kind(p)], on = visible(p), me = selected === feature.id;
        return { color: me ? '#0f172a' : c[0], weight: me ? 3 : (p.x || p.p ? 1.6 : 0.8), fillColor: c[1], fillOpacity: on ? (p.x ? 0.55 : (p.p ? 0.45 : 0.18)) : 0.03, opacity: on ? 1 : 0.25 };
    }
    function restyle() { if (layer) layer.setStyle(style); }

    function show(el) { ['pi-hint', 'pi-results', 'pi-card'].forEach(function (id) { document.getElementById(id).hidden = id !== el; }); }
    function icon(state) { return '<svg class="pi-svg"><use href="#' + (state === 'ok' ? 'i-ok' : 'i-alert') + '"/></svg>'; }
    function renderCard(c) {
        var fact = function (label, value) { return '<div><dt>' + label + '</dt><dd>' + (value ? esc(fa(value)) : '—') + '</dd></div>'; };
        var rows = c.status.map(function (s) { return '<li class="is-' + s.state + '">' + icon(s.state) + '<span>' + esc(fa(s.text)) + '</span></li>'; }).join('');
        var el = document.getElementById('pi-card');
        el.innerHTML = '<h2>ملک شماره‌ی ' + esc(fa(c.number || '—')) + '</h2><span class="pi-code">' + esc(fa(c.code || '')) + '</span>' +
            '<dl class="pi-facts">' + fact('بلوک', c.block) + fact('محله', c.zone_name) + fact('شماره‌ی قطعه‌ی تفکیکی', c.lot) + fact('مساحت (مترمربع)', c.area) +
            '<div style="grid-column:1/-1"><dt>کاربری</dt><dd>' + esc(c.land_use || '—') + '</dd></div></dl>' +
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
        if (feature && fly) { map.fitBounds(feature.getBounds(), { maxZoom: 19, padding: [60, 60] }); }
        fetch(config.urls.parcel.replace(/0\/$/, id + '/'), { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) { renderCard(d.parcel); });
    }

    function counts(features) {
        var n = { all: features.length, plan: 0, exempt: 0, clear: 0 };
        features.forEach(function (f) { var p = f.properties; if (p.p) n.plan++; if (p.x) n.exempt++; if (!p.p && !p.x) n.clear++; });
        Object.keys(n).forEach(function (k) { document.getElementById('pi-n-' + k).textContent = fa(n[k]); });
    }

    fetch(config.urls.data, { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (data) {
        layer = L.geoJSON(data, {
            style: style,
            onEachFeature: function (feature, lyr) {
                byId[feature.id] = lyr;
                lyr.on('click', function () { select(feature.id, false); });
            }
        }).addTo(map);
        map.fitBounds(layer.getBounds(), { padding: [20, 20] });
        counts(data.features);
        document.getElementById('pi-loading').hidden = true;
    }).catch(function () { document.getElementById('pi-loading').textContent = 'بارگذاری نقشه انجام نشد؛ صفحه را دوباره باز کنید.'; });

    document.querySelectorAll('.pi-chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            filter = chip.getAttribute('data-filter');
            document.querySelectorAll('.pi-chip').forEach(function (c) { c.classList.toggle('is-on', c === chip); });
            restyle();
        });
    });

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
                return '<li><button type="button" data-id="' + c.id + '">ملک ' + esc(fa(c.number)) + ' · بلوک ' + esc(fa(c.block)) + '<small>' + esc(fa(c.code)) + ' · ' + esc(c.land_use || '') + '</small></button></li>';
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
