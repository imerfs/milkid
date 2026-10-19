/* Persian numerals, rial formatting and the money arithmetic of the trade screens, kept free of the page so Node can test them
   (see static/js/tests). In the browser it is the global AccMoney; the accountant workspace scripts read it. */
(function (root) {
    var FA = '۰۱۲۳۴۵۶۷۸۹';

    function toLatin(text) {
        return String(text).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/[٠-٩]/g, function (d) { return d.charCodeAt(0) - 1632; })
            .replace(/[٬,،\s]/g, '').replace(/٫/g, '.').replace(/×/g, '*').replace(/÷/g, '/').replace(/−/g, '-').replace(/٪/g, '%');
    }
    function toFa(text) { return String(text).replace(/\d/g, function (d) { return FA[d]; }); }
    function num(text) { var n = parseFloat(toLatin(text || '')); return isNaN(n) ? 0 : n; }
    // 1250000 -> ۱٬۲۵۰٬۰۰۰
    function fmtRial(n) { return toFa(Math.round(n).toLocaleString('en')).replace(/,/g, '٬'); }
    // what a money box shows while typing: digits only, grouped, '' when empty
    function groupDigits(text) {
        var digits = toLatin(text).replace(/\D/g, '');
        return digits ? fmtRial(parseInt(digits, 10)) : '';
    }

    // a line's total in rials: quantity x unit price, less the line discount
    function lineTotal(qty, price, discount) { return Math.round(num(qty) * num(price)) - num(discount); }
    // selling price that gives `pct` percent profit over the buying price
    function sellFromMargin(buy, pct) { return Math.round(num(buy) * (1 + num(pct) / 100)); }
    // profit percent (one decimal) of a selling price over the buying price; null without a buying price
    function marginFromSell(buy, sell) {
        var b = num(buy);
        return b > 0 ? Math.round((num(sell) / b - 1) * 1000) / 10 : null;
    }
    // expected profit of a purchase line sold at the selling price
    function lineProfit(qty, buy, sell) { return Math.round((num(sell) - num(buy)) * num(qty)); }

    function fold(text) {
        return String(text).replace(/[۰-۹]/g, function (d) { return FA.indexOf(d); }).replace(/ي/g, 'ی').replace(/ك/g, 'ک').toLowerCase();
    }
    // products matching every word typed (name, code or barcode); out-of-stock ones only when asked
    function matchProducts(products, query, showAll) {
        var tokens = fold(query).split(/\s+/).filter(Boolean);
        return products.filter(function (p) {
            if (!showAll && !(p.stock > 0)) return false;
            var hay = fold(p.name + ' ' + p.code + ' ' + p.barcode);
            return tokens.every(function (t) { return hay.indexOf(t) !== -1; });
        });
    }

    var api = { toLatin: toLatin, toFa: toFa, num: num, fmtRial: fmtRial, groupDigits: groupDigits, lineTotal: lineTotal,
                sellFromMargin: sellFromMargin, marginFromSell: marginFromSell, lineProfit: lineProfit, matchProducts: matchProducts };
    root.AccMoney = api;
    if (typeof module !== 'undefined' && module.exports) module.exports = api;

    if (typeof document !== 'undefined') {      // inputs marked data-money show their value grouped while typing
        document.addEventListener('input', function (e) {
            if (e.target.matches && e.target.matches('[data-money]')) e.target.value = groupDigits(e.target.value);
        });
        document.addEventListener('htmx:afterSettle', function () {
            document.querySelectorAll('[data-money]').forEach(function (i) { if (i.value) i.value = groupDigits(i.value); });
        });
    }
})(typeof window !== 'undefined' ? window : globalThis);
