"""The dehyari's «فرم محاسبه عوارض و بهای خدمات»: the rates of each street width and the calculation of the 39 rows.

The rates come from the dehyari's eleven workbooks (one per street width, ``معبر 4-6`` … ``معبر 30 به بالا``). The workbooks share one layout; what differs
between them is the council factor B, the value rates of rows 26-31 (land added to the village limits, change of land use), the kerb and street-preparation
rates (rows 33-34). The land values and the P coefficients are the same in all of them. Every amount is worked out with decimals and rounded to the rial;
the sample of the dehyari (a plot on an 8 m street, 72.28 m² ground floor, 64 m² first floor, 79.41 m² plot) comes to 851,874,240 rials, as on the sheet.
"""
from decimal import ROUND_HALF_UP, Decimal

# key: (label, street width used for the street preparation row, B, join, change, services, kerb, preparation, preparation factor)
WIDTHS = {
    '4-6': ('معبر ۴ تا ۶ متری', 6, '1.4', 29_000_000, 0, 0, 0, 1_500_000, '0.5'),
    '8': ('معبر ۸ متری', 8, '1.4', 34_000_000, 0, 0, 7_500_000, 1_500_000, '0.5'),
    '10': ('معبر ۱۰ متری', 10, '1.7', 34_000_000, 0, 0, 7_500_000, 1_500_000, '0.5'),
    '12': ('معبر ۱۲ متری', 12, '1.8', 38_000_000, 50_000_000, 88_000_000, 12_500_000, 1_500_000, '0.5'),
    '14': ('معبر ۱۴ متری', 14, '1.8', 41_000_000, 65_000_000, 106_000_000, 12_500_000, 1_500_000, '0.5'),
    '16': ('معبر ۱۶ متری', 16, '1.9', 44_000_000, 75_000_000, 119_000_000, 12_500_000, 1_500_000, '0.5'),
    '18': ('معبر ۱۸ متری', 18, '1.9', 46_000_000, 75_000_000, 121_000_000, 17_500_000, 1_500_000, '0.5'),
    '20': ('معبر ۲۰ متری', 20, '2.1', 50_000_000, 78_000_000, 128_000_000, 17_500_000, 1_500_000, '0.5'),
    '25': ('معبر ۲۵ متری', 25, '2.1', 51_000_000, 84_000_000, 135_000_000, 20_000_000, 1_500_000, '0.5'),
    '30': ('معبر ۳۰ متری', 30, '2.4', 56_000_000, 87_000_000, 143_000_000, 20_000_000, 1_500_000, '1'),
    '30+': ('معبر بالاتر از ۳۰ متر (بلوار حافظ)', 30, '2.8', 57_000_000, 93_000_000, 150_000_000, 20_000_000, 1_500_000, '1'),
}

FLOOR_TITLES = ('پیلوت، زیرزمین', 'طبقه همکف', 'طبقه اول', 'طبقه دوم و بالاتر', 'پیش‌آمدگی و بالکن اول', 'پیش‌آمدگی و بالکن دوم و بالاتر')
# group: (title, land value P in rials, the P coefficients of the six rows)
GROUPS = (
    ('res', 'مسکونی', 220_000, ('5', '6.5', '8', '9', '80', '85')),
    ('com', 'تجاری', 440_000, ('8', '10', '11', '11', '80', '85')),
    ('svc', 'خدماتی - کارگاهی', 440_000, ('5', '7', '8', '9', '80', '85')),
    ('ind', 'صنعتی - تاسیساتی', 220_000, ('5', '5', '7', '8', '80', '85')),
)
FENCE_RATE = 350_000
ANNUAL_RATE, ANNUAL_FACTOR = 220_000, '0.4'
USE_FACTOR = '0.14'
CHANGE_ROWS = (27, 28, 29, 30, 31)
CHANGE_TITLES = {
    27: 'عوارض ارزش افزوده ناشی از تغییرکاربری مسکونی به تجاری',
    28: 'عوارض ارزش افزوده ناشی از تغییرکاربری اداری، درمانی، ورزشی، آموزشی، فرهنگی، مذهبی به مسکونی',
    29: 'عوارض ارزش افزوده ناشی از تغییرکاربری تاسیسات، حمل ونقل، انبار و فضای سبز به مسکونی',
    30: 'عوارض ارزش افزوده ناشی از تغییرکاربری اداری، درمانی، ورزشی، آموزشی، فرهنگی، مذهبی به خدماتی - کارگاهی',
    31: 'عوارض ارزش افزوده ناشی از تغییرکاربری تاسیسات، حمل ونقل، انبار و فضای سبز به خدماتی - کارگاهی',
}
# the rows charged a fixed amount (with the 10 % tax already added, as the sheet prints them): row -> (title, default)
FIXED_ROWS = {
    32: ('بهای کارشناسی', 4_400_000), 35: ('تشکیل پرونده', 1_100_000), 36: ('بهای خدمات ایمنی و آتش‌نشانی', 4_400_000),
    37: ('بهای خدمات مدیریت پسماند و رفت و روب', 4_400_000), 38: ('بهای خدمات جمع‌آوری سگ‌های پرسه‌زن', 1_100_000),
}
TAX = Decimal('1.1')


def money(value):
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rates(width):
    label, street, b, join, change, services, kerb, prep, prep_f = WIDTHS[width]
    return {'label': label, 'street': street, 'b': b, 'join': join, 'change': change, 'services': services, 'kerb': kerb, 'prep': prep, 'prep_f': prep_f}


def defaults(width):
    """The inputs of a new sheet for a street width (all areas empty, the council factor and the fixed rows from the tables)."""
    r = rates(width)
    out = {'width': width, 'b': r['b'], 'fence': '0', 'join': '0', 'curb_len': '0', 'prep_w': str(r['street']), 'annual': '0'}
    for key, _, _, _ in GROUPS:
        for i in range(6):
            out[f'a_{key}_{i}'] = '0'
    for no in CHANGE_ROWS:
        out[f'chg_{no}'] = '0'
    for no, (_, amount) in FIXED_ROWS.items():
        out[f'fx_{no}'] = str(amount)
    return out


def _d(value):
    try:
        return Decimal(str(value or '0'))
    except Exception:           # pylint: disable=broad-except
        return Decimal(0)


def compute(inputs):
    """The 39 rows and their total from the sheet's inputs: ``[{no, group, title, amount}]`` and the sum in rials."""
    r = rates(inputs['width'])
    b = _d(inputs.get('b'))
    rows, no = [], 0
    for key, title, land, coefs in GROUPS:
        for i, floor in enumerate(FLOOR_TITLES):
            no += 1
            rows.append({'no': no, 'group': title, 'title': f'عوارض {"احداث بنا " if i < 4 else ""}{floor}',
                         'area': inputs.get(f'a_{key}_{i}', '0'), 'amount': money(_d(coefs[i]) * land * b * _d(inputs.get(f'a_{key}_{i}')))})
    rows.append({'no': 25, 'group': 'حصارکشی', 'title': 'عوارض حصارکشی', 'area': inputs.get('fence', '0'), 'amount': money(FENCE_RATE * _d(inputs.get('fence')))})
    rows.append({'no': 26, 'group': 'الحاق', 'title': 'سهم خدمات عمومی اراضی الحاقی به محدوده از مزروعی به مسکونی', 'area': inputs.get('join', '0'),
                 'amount': money(r['join'] * _d(USE_FACTOR) * _d(inputs.get('join')))})
    for no in CHANGE_ROWS:
        rate = r['change'] if no == 27 else (r['join'] if no in (28, 29) else r['services'])
        factor = Decimal(0) if no == 27 else _d(USE_FACTOR)
        rows.append({'no': no, 'group': 'ارزش افزوده تغییرکاربری', 'title': CHANGE_TITLES[no], 'area': inputs.get(f'chg_{no}', '0'),
                     'amount': money(rate * factor * _d(inputs.get(f'chg_{no}')))})
    for no in (32, 35, 36, 37, 38):
        title, _ = FIXED_ROWS[no]
        rows.append({'no': no, 'group': 'کارشناسی، فنی، آموزشی' if no < 36 else 'سایر', 'title': title, 'area': '', 'amount': money(inputs.get(f'fx_{no}'))})
    curb_len = _d(inputs.get('curb_len'))
    rows.append({'no': 33, 'group': 'کارشناسی، فنی، آموزشی', 'title': 'بهای خدمات جدولگذاری', 'area': inputs.get('curb_len', '0'),
                 'amount': money(curb_len * r['kerb'] * TAX)})
    rows.append({'no': 34, 'group': 'کارشناسی، فنی، آموزشی', 'title': 'بهای خدمات زیرسازی', 'area': inputs.get('curb_len', '0'),
                 'amount': money(_d(inputs.get('prep_w')) * r['prep'] * _d(r['prep_f']) * curb_len * TAX)})
    rows.append({'no': 39, 'group': 'سایر', 'title': 'عوارض سالیانه املاک و مستحدثات (سطح روستا)', 'area': inputs.get('annual', '0'),
                 'amount': money(_d(ANNUAL_FACTOR) * ANNUAL_RATE * _d(inputs.get('annual')))})
    rows.sort(key=lambda row: row['no'])
    return rows, sum(row['amount'] for row in rows)
