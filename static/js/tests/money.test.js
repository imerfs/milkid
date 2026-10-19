// Run with: npm run test:js  (Node's built-in test runner, no dependencies)
const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../accounting-money.js');

test('Persian digits and separators are read back as plain numbers', () => {
    assert.equal(M.toLatin('۱٬۲۵۰٬۰۰۰'), '1250000');
    assert.equal(M.toLatin('١٢٣'), '123');
    assert.equal(M.num('۱٬۲۵۰٫۵'), 1250.5);
    assert.equal(M.num(''), 0);
    assert.equal(M.num('abc'), 0);
});

test('rials are shown with Persian digits and Persian thousands separators', () => {
    assert.equal(M.fmtRial(1250000), '۱٬۲۵۰٬۰۰۰');
    assert.equal(M.fmtRial(0), '۰');
    assert.equal(M.fmtRial(999.6), '۱٬۰۰۰');
    assert.equal(M.toFa('Total 12'), 'Total ۱۲');
});

test('a money box groups what is typed and drops everything but digits', () => {
    assert.equal(M.groupDigits('1250000'), '۱٬۲۵۰٬۰۰۰');
    assert.equal(M.groupDigits('۱٬۲۵۰'), '۱٬۲۵۰');
    assert.equal(M.groupDigits('12ab5'), '۱۲۵');
    assert.equal(M.groupDigits(''), '');
    assert.equal(M.groupDigits('x'), '');
});

test('line totals and the profit percent work both ways', () => {
    assert.equal(M.lineTotal('۴', '۱٬۰۰۰', '۱۰۰'), 3900);
    assert.equal(M.lineTotal('2.5', '1000', ''), 2500);
    assert.equal(M.sellFromMargin('۱٬۰۰۰٬۰۰۰', '25'), 1250000);
    assert.equal(M.marginFromSell('1000000', '1500000'), 50);
    assert.equal(M.marginFromSell('3', '4'), 33.3);
    assert.equal(M.marginFromSell('0', '100'), null);
    assert.equal(M.lineProfit('10', '1000000', '1250000'), 2500000);
    assert.equal(M.lineProfit('10', '1000', '900'), -1000);
});

test('product search matches every word, in any order, and hides out-of-stock unless asked', () => {
    const products = [
        { name: 'برنج ایرانی', code: 'P1', barcode: '111', stock: 5 },
        { name: 'روغن مایع', code: 'P2', barcode: '222', stock: 0 },
        { name: 'برنج پاکستانی', code: 'P3', barcode: '333', stock: 2 },
    ];
    assert.deepEqual(M.matchProducts(products, 'برنج', false).map(p => p.code), ['P1', 'P3']);
    assert.deepEqual(M.matchProducts(products, 'ایرانی برنج', false).map(p => p.code), ['P1']);
    assert.deepEqual(M.matchProducts(products, 'روغن', false), []);
    assert.deepEqual(M.matchProducts(products, 'روغن', true).map(p => p.code), ['P2']);
    assert.deepEqual(M.matchProducts(products, '۲۲۲', true).map(p => p.code), ['P2']);        // Persian digits find the barcode
    assert.deepEqual(M.matchProducts(products, 'p3', false).map(p => p.code), ['P3']);
    assert.equal(M.matchProducts(products, '', false).length, 2);
    assert.deepEqual(M.matchProducts(products, 'بر پاک', false).map(p => p.code), ['P3']);      // part of a word is enough
});

test('Arabic yeh and kaf match their Persian forms', () => {
    const products = [{ name: 'کیسه', code: 'K', barcode: '', stock: 1 }, { name: 'ایرانی', code: 'I', barcode: '', stock: 1 }];
    assert.deepEqual(M.matchProducts(products, 'كيسه', false).map(p => p.code), ['K']);
    assert.deepEqual(M.matchProducts(products, 'ايراني', false).map(p => p.code), ['I']);
});

test('the shared rial table (same cases the Python tests use)', () => {
    const cases = require('./rial-cases.json');
    for (const c of cases.show) assert.equal(M.fmtRial(c.amount), c.shown, `show ${c.amount}`);
    for (const c of cases.read) assert.equal(M.num(c.typed), c.amount, `read ${JSON.stringify(c.typed)}`);
    for (const c of cases.show) assert.equal(M.groupDigits(String(c.amount)), c.shown, `group ${c.amount}`);
});
