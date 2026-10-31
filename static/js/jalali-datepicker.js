/**
 * MelkID Persian date field: one component for every date on the site.
 *
 * Every date input (class .jalali-date / .jalali-datetime, type="date" / "datetime-local", or a text input whose name is "date" or ends in "_date") becomes the
 * same field: a Jalali date typed as ۱۴۰۵/۰۷/۲۶ (Persian or Latin digits) or picked from a calendar (Saturday first, Friday marked, today marked, month and
 * year jump, today / clear buttons). The format is always YYYY/MM/DD with Persian digits. A type="date" input keeps its ISO value for the server in a hidden
 * field of the same name, so the pages that expect Gregorian dates keep working.
 *
 * Options (data attributes): data-jmin / data-jmax = "YYYY/MM/DD" limits; name containing "birth" = no future dates and the calendar opens on a past year;
 * data-nopicker = leave the input alone.
 * The calendar icon is "calendar" from Keyline Icons (MIT, https://keylineicons.com). The calendar's behaviour follows the common Persian calendar UX.
 */
(function () {
    'use strict';

    var MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
    var WEEK = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
    var FA = '۰۱۲۳۴۵۶۷۸۹';
    var ICON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round"><path d="M6 5H18C19.6569 5 21 6.34315 21 8V18C21 19.6569 19.6569 21 18 21H6C4.34315 21 3 19.6569 3 18V8C3 ' +
        '6.34315 4.34315 5 6 5ZM7 11H17M8 3V7M16 3V7"></path></svg>';

    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function toFa(s) { return String(s).replace(/\d/g, function (d) { return FA[d]; }); }
    function toEn(s) {
        return String(s).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/[٠-٩]/g, function (d) { return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); });
    }

    // Gregorian <-> Jalali (the public-domain algorithm of Roozbeh Pournader's jdf)
    function g2j(gy, gm, gd) {
        var gdm = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
        var jy = gy > 1600 ? 979 : 0;
        gy -= gy > 1600 ? 1600 : 621;
        var gy2 = gm > 2 ? gy + 1 : gy;
        var days = 365 * gy + Math.floor((gy2 + 3) / 4) - Math.floor((gy2 + 99) / 100) + Math.floor((gy2 + 399) / 400) - 80 + gd + gdm[gm - 1];
        jy += 33 * Math.floor(days / 12053);
        days %= 12053;
        jy += 4 * Math.floor(days / 1461);
        days %= 1461;
        if (days > 365) { jy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
        var jm = days < 186 ? 1 + Math.floor(days / 31) : 7 + Math.floor((days - 186) / 30);
        var jd = 1 + (days < 186 ? days % 31 : (days - 186) % 30);
        return [jy, jm, jd];
    }
    function j2g(jy, jm, jd) {
        var gy = jy > 979 ? 1600 : 621;
        jy -= jy > 979 ? 979 : 0;
        var days = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + 78 + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
        gy += 400 * Math.floor(days / 146097);
        days %= 146097;
        if (days > 36524) {
            days -= 1;
            gy += 100 * Math.floor(days / 36524);
            days %= 36524;
            if (days >= 365) days += 1;
        }
        gy += 4 * Math.floor(days / 1461);
        days %= 1461;
        if (days > 365) { gy += Math.floor((days - 1) / 365); days = (days - 1) % 365; }
        var gd = days + 1;
        var leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
        var sal = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
        var gm = 0;
        while (gm < 13 && gd > sal[gm]) { gd -= sal[gm]; gm++; }
        return [gy, gm, gd];
    }
    function daysIn(y, m) {
        if (m <= 6) return 31;
        if (m <= 11) return 30;
        var g = j2g(y, 12, 30), back = g2j(g[0], g[1], g[2]);
        return back[0] === y && back[1] === 12 && back[2] === 30 ? 30 : 29;
    }
    function weekday(y, m, d) {                          // 0 = Saturday ... 6 = Friday
        var g = j2g(y, m, d);
        return (new Date(g[0], g[1] - 1, g[2]).getDay() + 1) % 7;
    }
    function today() {
        var n = new Date();
        return g2j(n.getFullYear(), n.getMonth() + 1, n.getDate());
    }
    function parse(text) {
        var m = toEn(text).trim().match(/^(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})$/);
        if (!m) return null;
        var y = +m[1], mo = +m[2], d = +m[3];
        if (mo < 1 || mo > 12 || d < 1 || d > daysIn(y, mo)) return null;
        return [y, mo, d];
    }
    function show(j) { return toFa(j[0] + '/' + pad(j[1]) + '/' + pad(j[2])); }
    function cmp(a, b) { return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; }
    function iso(j) { var g = j2g(j[0], j[1], j[2]); return g[0] + '-' + pad(g[1]) + '-' + pad(g[2]); }
    function fromIso(text) {
        var m = String(text || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
        return m ? g2j(+m[1], +m[2], +m[3]) : null;
    }

    // ---- which inputs are date inputs ----
    var NAME = /(^|_)date(_|$)/i;
    function isDateInput(el) {
        if (!el || el.tagName !== 'INPUT' || el.dataset.jd || el.hasAttribute('data-nopicker') || el.readOnly || el.disabled) return false;
        if (el.closest && el.closest('.jd-pop')) return false;
        var type = (el.getAttribute('type') || 'text').toLowerCase();
        if (['text', 'date', 'datetime-local', ''].indexOf(type) < 0) return false;
        return el.classList.contains('jalali-date') || el.classList.contains('jalali-datetime') || type === 'date' || type === 'datetime-local' ||
            el.hasAttribute('data-jalali') || NAME.test(el.getAttribute('name') || '');
    }

    // ---- the calendar popup (one for the page) ----
    var pop = null, active = null;
    function limits(el) {
        var name = (el.getAttribute('name') || '') + ' ' + (el.id || '');
        var min = parse(el.dataset.jmin || ''), max = parse(el.dataset.jmax || '');
        if (!max && /birth/i.test(name)) max = today();
        return { min: min, max: max, birth: /birth/i.test(name) };
    }
    function build() {
        pop = document.createElement('div');
        pop.className = 'jd-pop';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', 'تقویم شمسی');
        pop.hidden = true;
        document.body.appendChild(pop);
        pop.addEventListener('mousedown', function (e) { if (e.target.tagName !== 'SELECT') e.preventDefault(); });
        pop.addEventListener('click', onPopClick);
        pop.addEventListener('change', onPopChange);
        document.addEventListener('mousedown', function (e) { if (active && !pop.contains(e.target) && e.target !== active.input && !active.wrap.contains(e.target)) close(); });
        document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && active) close(); });
        window.addEventListener('resize', function () { if (active) place(); });
        window.addEventListener('scroll', function () { if (active) place(); }, true);
    }
    function open(field) {
        if (!pop) build();
        active = field;
        var current = parse(field.input.value) || null;
        var t = today(), lim = limits(field.input);
        var view = current || (lim.birth ? [t[0] - 30, 1, 1] : t);
        field.view = [view[0], view[1]];
        render();
        pop.hidden = false;
        place();
    }
    function close() { if (pop) pop.hidden = true; active = null; }
    function place() {
        var r = active.input.getBoundingClientRect(), w = pop.offsetWidth || 288;
        var left = Math.min(Math.max(8, r.right - w), document.documentElement.clientWidth - w - 8) + window.pageXOffset;
        var h = pop.offsetHeight, top = r.bottom + window.pageYOffset + 6;
        if (r.bottom + h + 12 > window.innerHeight && r.top > h + 12) top = r.top + window.pageYOffset - h - 6;      // above only when it really fits
        pop.style.left = left + 'px';
        pop.style.top = top + 'px';
    }
    function render() {
        var f = active, y = f.view[0], m = f.view[1], lim = limits(f.input), t = today(), cur = parse(f.input.value);
        var from = lim.min ? lim.min[0] : (lim.birth ? 1300 : t[0] - 100), to = lim.max ? lim.max[0] : t[0] + 15;
        var years = '', months = '', i;
        for (i = to; i >= from; i--) years += '<option value="' + i + '"' + (i === y ? ' selected' : '') + '>' + toFa(i) + '</option>';
        for (i = 1; i <= 12; i++) months += '<option value="' + i + '"' + (i === m ? ' selected' : '') + '>' + MONTHS[i - 1] + '</option>';
        var html = '<div class="jd-head"><button type="button" class="jd-nav" data-go="1" aria-label="ماه بعد">&#8249;</button>' +
            '<select class="jd-sel" data-part="m" aria-label="ماه">' + months + '</select><select class="jd-sel" data-part="y" aria-label="سال">' + years + '</select>' +
            '<button type="button" class="jd-nav" data-go="-1" aria-label="ماه قبل">&#8250;</button></div><div class="jd-grid" role="grid">';
        for (i = 0; i < 7; i++) html += '<span class="jd-wd' + (i === 6 ? ' jd-fri' : '') + '">' + WEEK[i] + '</span>';
        var lead = weekday(y, m, 1), n = daysIn(y, m), d;
        for (i = 0; i < lead; i++) html += '<span></span>';
        for (d = 1; d <= n; d++) {
            var day = [y, m, d], cls = 'jd-day', off = (lim.min && cmp(day, lim.min) < 0) || (lim.max && cmp(day, lim.max) > 0);
            if ((lead + d - 1) % 7 === 6) cls += ' jd-fri';
            if (cmp(day, t) === 0) cls += ' jd-today';
            if (cur && cmp(day, cur) === 0) cls += ' jd-on';
            html += '<button type="button" class="' + cls + '" data-day="' + d + '"' + (off ? ' disabled' : '') + '>' + toFa(d) + '</button>';
        }
        html += '</div><div class="jd-foot"><button type="button" data-act="today">امروز</button><button type="button" data-act="clear">پاک کردن</button>' +
            '<button type="button" data-act="close">بستن</button></div>';
        pop.innerHTML = html;
    }
    function onPopChange(e) {
        if (!active || !e.target.dataset.part) return;
        var v = active.view;
        if (e.target.dataset.part === 'y') v[0] = +e.target.value; else v[1] = +e.target.value;
        render();
    }
    function onPopClick(e) {
        if (!active) return;
        var b = e.target.closest('button');
        if (!b) return;
        var v = active.view;
        if (b.dataset.go) {
            v[1] += +b.dataset.go;
            if (v[1] > 12) { v[1] = 1; v[0]++; }
            if (v[1] < 1) { v[1] = 12; v[0]--; }
            render();
        } else if (b.dataset.day) {
            commit(active, [v[0], v[1], +b.dataset.day]);
            close();
        } else if (b.dataset.act === 'today') {
            var lim = limits(active.input), t = today();
            if ((lim.max && cmp(t, lim.max) > 0) || (lim.min && cmp(t, lim.min) < 0)) return;
            commit(active, t);
            close();
        } else if (b.dataset.act === 'clear') {
            commit(active, null);
            close();
        } else if (b.dataset.act === 'close') {
            close();
        }
    }

    // ---- one field ----
    function sync(field) {
        var j = parse(field.input.value);
        if (field.hidden) {
            var time = field.time ? field.time.value : '';
            field.hidden.value = j ? (field.kind === 'dt' ? iso(j) + 'T' + (time || '00:00') : iso(j)) : '';
        }
    }
    function commit(field, j) {
        field.input.value = j ? show(j) : '';
        field.input.setCustomValidity('');
        field.input.classList.remove('jd-invalid');
        sync(field);
        ['input', 'change'].forEach(function (name) { field.input.dispatchEvent(new Event(name, { bubbles: true })); });
        if (field.hidden) field.hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function validate(field) {
        var text = field.input.value.trim();
        if (!text) { field.input.setCustomValidity(''); field.input.classList.remove('jd-invalid'); return; }
        var j = parse(text), lim = limits(field.input), msg = '';
        if (!j) msg = 'تاریخ را به شکل ۱۴۰۵/۰۷/۲۶ وارد کنید.';
        else if (lim.max && cmp(j, lim.max) > 0) msg = 'تاریخ نمی‌تواند از ' + show(lim.max) + ' دیرتر باشد.';
        else if (lim.min && cmp(j, lim.min) < 0) msg = 'تاریخ نمی‌تواند از ' + show(lim.min) + ' زودتر باشد.';
        field.input.setCustomValidity(msg);
        field.input.classList.toggle('jd-invalid', !!msg);
        if (!msg) field.input.value = show(j);
        sync(field);
    }
    function enhance(input) {
        if (!isDateInput(input)) return;
        var type = (input.getAttribute('type') || 'text').toLowerCase();
        var field = { input: input, kind: type === 'date' ? 'date' : (type === 'datetime-local' ? 'dt' : 'text'), view: [0, 1] };
        input.dataset.jd = '1';
        var start = input.value;
        var wrap = document.createElement('span');
        wrap.className = 'jd-wrap';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);
        field.wrap = wrap;
        if (field.kind !== 'text') {                      // the server keeps getting the Gregorian value it asked for
            var hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = input.name;
            input.removeAttribute('name');
            input.setAttribute('type', 'text');
            wrap.appendChild(hidden);
            field.hidden = hidden;
            if (field.kind === 'dt') {
                var time = document.createElement('input');
                time.type = 'time';
                time.className = (input.className ? input.className + ' ' : '') + 'jd-time';
                time.setAttribute('aria-label', 'ساعت');
                var m = String(start || '').match(/T(\d{2}:\d{2})/);
                time.value = m ? m[1] : '';
                time.addEventListener('change', function () { sync(field); });
                wrap.appendChild(time);
                field.time = time;
            }
            var j0 = fromIso(start);
            input.value = j0 ? show(j0) : '';
        } else {
            var parsed = parse(start);
            if (parsed) input.value = show(parsed);
        }
        input.setAttribute('autocomplete', 'off');
        input.setAttribute('inputmode', 'numeric');
        input.setAttribute('dir', 'ltr');
        if (!input.placeholder) input.placeholder = toFa('1405/07/26');
        input.classList.add('jd-input');
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'jd-icon';
        button.setAttribute('aria-label', 'انتخاب تاریخ');
        button.tabIndex = -1;
        button.innerHTML = ICON;
        wrap.appendChild(button);
        button.addEventListener('click', function () { if (active === field) close(); else open(field); });
        input.addEventListener('focus', function () { open(field); });
        input.addEventListener('click', function () { if (!active || active !== field) open(field); });
        input.addEventListener('input', function () {
            var j = parse(input.value);
            if (j) { field.view = [j[0], j[1]]; if (active === field) render(); }
            sync(field);
        });
        input.addEventListener('blur', function () { setTimeout(function () { validate(field); }, 120); });
        input.addEventListener('keydown', function (e) { if (e.key === 'Enter' && active === field) { validate(field); close(); } });
        sync(field);
    }

    function scan(root) {
        var list = (root || document).querySelectorAll('input');
        for (var i = 0; i < list.length; i++) enhance(list[i]);
    }
    function init() {
        scan(document);
        if (window.MutationObserver) {
            new MutationObserver(function (changes) {
                changes.forEach(function (c) {
                    c.addedNodes.forEach(function (n) {
                        if (n.nodeType !== 1) return;
                        if (n.tagName === 'INPUT') enhance(n); else if (n.querySelectorAll) scan(n);
                    });
                });
            }).observe(document.body, { childList: true, subtree: true });
        }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

    window.JalaliDatePicker = {
        init: function () { scan(document); },
        toJalali: g2j, toGregorian: j2g, parse: parse, format: show, daysInMonth: daysIn, today: today,
        formatDate: function (d) { d = d instanceof Date ? d : new Date(d); return show(g2j(d.getFullYear(), d.getMonth() + 1, d.getDate())); }
    };
})();
