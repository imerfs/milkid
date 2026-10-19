"""The accountant workspace tabs: one definition per tab that the menu (desktop and phone), the access levels, the panel
renderer and the tests all read. Adding a tab means adding one ``Tab`` line here (plus its builder and template).

Pure data: no Django or view imports, so every layer can import it."""
from collections import namedtuple

# key, label, icon, needs a fiscal year, page subtitle, access area ('' = always allowed), menu group ('' = top),
# menu sub-heading, short menu label ('' = label), phone-menu label (None = not on the phone menu; '' = the menu label),
# drawn by the generic register template
Tab = namedtuple('Tab', 'key label icon needs_year subtitle area group section nav_label mobile register')

GROUPS = [
    ('accounting', 'حسابداری', 'book'),
    ('reports', 'گزارش\u200cها', 'chart-pie'),
    ('income', 'درآمد', 'coins'),
    ('payroll', 'حقوق و دستمزد', 'users'),
    ('settings', 'پرداخت\u200cها و تنظیمات', 'gear'),
]   # key, label, icon (menu order)

TAB_LIST = [
    Tab('overview', 'نمای کلی', 'gauge-high', True, 'وضعیت مالی سال جاری و کارهای باز، یک\u200cجا.', '', '', '', '', '', False),
    Tab('vouchers', 'اسناد حسابداری', 'file-invoice', True, 'ثبت، ویرایش و قطعی\u200cکردن اسناد.', 'vouchers', 'accounting', '', '', 'اسناد', False),
    Tab('statuschange', 'تغییر وضعیت اسناد', 'check-double', True, 'قطعی یا موقت\u200cکردن گروهی اسناد بر اساس بازه شماره.', 'vouchers', 'accounting', '', '', None, False),
    Tab('images', 'تصاویر اسناد', 'images', True, 'اسکن و تصویر مدارک پشتوانه اسناد.', 'vouchers', 'accounting', '', '', None, True),
    Tab('bills', 'فیش\u200cهای نقدی', 'receipt', True, 'صدور فیش و ثبت پرداخت\u200cها.', 'bills', 'accounting', '', '', '', False),
    Tab('parties', 'طرف\u200cحساب\u200cها', 'address-book', False, 'اشخاص و سازمان\u200cهایی که با دهیاری حساب دارند.', 'master', 'accounting', '', '', '', False),
    Tab('accounts', 'سرفصل حساب\u200cها', 'sitemap', False, 'درخت حساب\u200cهای دهیاری.', 'master', 'accounting', '', '', 'سرفصل\u200cها', False),
    Tab('credit', 'تامین اعتبار', 'hand-holding-dollar', True, 'رزرو اعتبار بودجه برای حساب\u200cهای مصرف، بدون عبور از بودجه مصوب.', 'budget', 'accounting', '', '', '', True),
    Tab('contracts', 'قراردادها', 'file-signature', True, 'قراردادها، صورت\u200cوضعیت\u200cها و کسورات پیمانکار.', 'contracts', 'accounting', '', '', '', True),
    Tab('guarantees', 'ضمانت\u200cنامه\u200cها', 'shield-halved', False, 'ضمانت\u200cنامه\u200cها، چک و سفته\u200cهای دریافتی و سررسید آن\u200cها.', 'contracts', 'accounting', '', '', '', True),
    Tab('assets', 'دارایی\u200cهای ثابت', 'building', True, 'ثبت دارایی، استهلاک سالانه با سند حسابداری و خروج یا فروش.', 'assets', 'accounting', '', '', '', False),
    Tab('recon', 'مغایرت\u200cگیری بانک', 'building-columns', True, 'تیک\u200cزدن گردش بانک و صندوق و مقایسه با صورت\u200cحساب بانک.', 'yearend', 'accounting', '', '', '', False),
    Tab('yearend', 'عملیات سال مالی', 'flag-checkered', True, 'سند بستن حساب\u200cهای موقت، اختتامیه، افتتاحیه و بستن سال.', 'yearend', 'accounting', '', '', '', False),
    Tab('reports', 'گزارش\u200cگیری', 'file-lines', True, 'گزارش اسناد، دفاتر، فیش\u200cها، تقسیط، ضمانت\u200cنامه\u200cها و ... با خروجی اکسل.', 'reports', 'reports', '', '', 'گزارش\u200cها', False),
    Tab('builder', 'گزارش\u200cساز و تحلیل\u200cگر', 'table-cells', True, 'گزارش دلخواه از اسناد، فیش\u200cها و اقساط، به\u200cصورت جدول یا ماتریس، با خروجی اکسل.', 'reports', 'reports', '', 'گزارش\u200cساز', '', False),
    Tab('charts', 'نمودارها', 'chart-column', True, 'منابع و مصارف ماهانه، بزرگ\u200cترین حساب\u200cها و بودجه در برابر عملکرد.', 'reports', 'reports', '', '', '', False),
    Tab('trial', 'تراز آزمایشی', 'scale-balanced', True, 'جمع بدهکار و بستانکار همه حساب\u200cها.', 'reports', 'reports', '', '', '', False),
    Tab('budget', 'بودجه و عملکرد', 'chart-pie', True, 'بودجه مصوب در برابر عملکرد هر حساب.', 'budget', 'reports', '', '', 'بودجه', False),
    Tab('statements', 'صورت\u200cهای مالی', 'file-invoice-dollar', True, 'صورت منابع و مصارف و ترازنامه تا تاریخ دلخواه.', 'reports', 'reports', '', '', '', False),
    Tab('plans', 'تقسیط', 'calendar-check', True, 'پرونده\u200cهای تقسیط بدهی، اقساط و پرداخت\u200cها.', 'income', 'income', '', '', '', True),
    Tab('received', 'خزانه اسناد دریافتی', 'money-check', True, 'چک و سفته\u200cهای دریافتی: ارسال به خزانه، وصول یا برگشت.', 'income', 'income', '', '', 'خزانه دریافتی', True),
    Tab('transport', 'درآمد حمل و نقل', 'truck', True, 'عوارض و بهای خدمات حمل و نقل.', 'income', 'income', '', '', 'حمل و نقل', True),
    Tab('planimages', 'تصاویر پرونده تقسیط', 'images', True, 'مدارک و نامه\u200cهای پرونده\u200cهای تقسیط.', 'income', 'income', '', '', None, True),
    Tab('trade_products', 'کالاها', 'boxes-stacked', True, 'کالاها، قیمت\u200cها و موجودی.', 'trade', 'income', 'بازرگانی و انبار', '', '', True),
    Tab('trade_invoices', 'فاکتورها', 'file-invoice', True, 'فروش، خرید، برگشت\u200cها، پیش\u200cفاکتور و سفارش.', 'trade', 'income', 'بازرگانی و انبار', '', '', True),
    Tab('trade_pos', 'فروش سریع', 'cash-register', True, 'صندوق فروش: بارکد، سبد، دریافت و صدور فاکتور.', 'trade', 'income', 'بازرگانی و انبار', '', '', False),
    Tab('trade_stock', 'موجودی انبار', 'warehouse', True, 'موجودی و ارزش هر کالا به تفکیک انبار و کاردکس.', 'trade', 'income', 'بازرگانی و انبار', '', '', False),
    Tab('trade_docs', 'اسناد انبار', 'dolly', True, 'رسید، حواله، انتقال، تعدیل و انبارگردانی.', 'trade', 'income', 'بازرگانی و انبار', '', '', True),
    Tab('trade_production', 'تولید', 'industry', True, 'فرمول ساخت، برآورد و ثبت تولید.', 'trade', 'income', 'بازرگانی و انبار', '', '', False),
    Tab('trade_consign', 'امانی', 'handshake', True, 'کالای امانی داده\u200cشده و گرفته\u200cشده.', 'trade', 'income', 'بازرگانی و انبار', '', '', True),
    Tab('trade_profit', 'سود کالا', 'chart-line', True, 'سود ناخالص هر کالا، فروش به تفکیک ویزیتور و طرف حساب.', 'trade', 'income', 'بازرگانی و انبار', '', '', False),
    Tab('pstaff', 'اطلاعات پرسنل', 'users', False, 'پرسنل، مزایای ماهانه و بدهی\u200cهای هر نفر.', 'payroll', 'payroll', '', '', 'پرسنل', True),
    Tab('pattendance', 'کارکرد ماهانه', 'clock', False, 'کارکرد، غیبت، اضافه کار و شب کاری هر ماه.', 'payroll', 'payroll', '', 'کارکرد', '', True),
    Tab('pmission', 'ماموریت', 'plane', False, 'ماموریت\u200cهای پرسنل و هزینه\u200cهای آن\u200cها.', 'payroll', 'payroll', '', '', None, True),
    Tab('pspecialallow', 'مزایای مخصوص', 'gift', False, 'مزایایی که به همه پرسنل یک گروه محاسباتی داده می\u200cشود.', 'payroll', 'payroll', '', '', None, True),
    Tab('pspecialdebt', 'بدهی مخصوص', 'file-invoice-dollar', False, 'کسوراتی که از همه پرسنل یک گروه محاسباتی کم می\u200cشود.', 'payroll', 'payroll', '', '', None, True),
    Tab('pmisc', 'پرداخت\u200cهای متفرقه', 'wallet', False, 'واریزی\u200cهای غیرحقوقی و علی\u200cالحساب هر ماه.', 'payroll', 'payroll', '', '', None, True),
    Tab('pworkers', 'کارگران روزمزد', 'helmet-safe', False, 'کارگران روزمزد و کارکرد ماهانه آن\u200cها.', 'payroll', 'payroll', '', '', None, True),
    Tab('peidi', 'اطلاعات عیدی', 'gift', False, 'تنظیم و محاسبه عیدی سالانه پرسنل.', 'payroll', 'payroll', '', '', None, True),
    Tab('pcalc', 'نحوه محاسبات فردی', 'sliders', False, 'نرخ\u200cها و مبالغ اختصاصی هر فرد که جایگزین تنظیمات عمومی می\u200cشود.', 'payroll', 'payroll', '', 'محاسبات فردی', None, True),
    Tab('prun', 'محاسبه و فیش حقوق', 'money-bill-wave', False, 'محاسبه ماهانه حقوق، فیش هر فرد، قطعی\u200cکردن و خروجی اکسل.', 'payroll', 'payroll', '', '', 'حقوق', True),
    Tab('psettings', 'تنظیمات حقوق', 'gear', False, 'نرخ بیمه، ضریب اضافه کار و سایر پارامترهای محاسبه.', 'payroll', 'payroll', '', '', None, True),
    Tab('payables', 'خزانه اسناد پرداختی', 'money-check-dollar', True, 'چک\u200cها و سفته\u200cهای صادرشده تا زمان پاس\u200cشدن.', 'contracts', 'settings', '', '', 'خزانه پرداختی', True),
    Tab('online', 'پرداخت\u200cهای آنلاین', 'credit-card', False, 'پرداخت\u200cهای شهروندان: تایید، رد و سابقه.', 'bills', 'settings', '', '', '', False),
    Tab('settings', 'تنظیمات مالی', 'sliders', False, 'مراکز هزینه، شرح\u200cهای استاندارد و امضاکنندگان.', 'master', 'settings', '', '', 'تنظیمات', False),
    Tab('setup', 'سال مالی و شروع کار', 'calendar-days', False, 'باز کردن سال مالی و ساخت سرفصل\u200cهای پیش\u200cفرض.', 'yearend', 'settings', '', '', 'سال مالی', False),
    Tab('tools', 'ابزارها', 'screwdriver-wrench', False, 'ماشین\u200cحساب، عدد به حروف، تبدیل تاریخ و اقساط وام.', '', 'settings', '', '', '', False),
    Tab('backup', 'پشتیبان\u200cگیری', 'database', True, 'نسخه پشتیبان از اطلاعات حسابداری دهیاری و بازیابی آن.', 'controls', 'settings', '', '', '', False),
    Tab('controls', 'قفل تاریخ و کنترل داده', 'shield-heart', True, 'قفل اسناد تا یک تاریخ و بررسی سلامت دفتر.', 'controls', 'settings', '', 'قفل و کنترل داده', '', False),
    Tab('audit', 'لاگ ممیزی', 'clock-rotate-left', True, 'چه کسی چه چیزی را کی تغییر داده؛ ورود و خروج کاربران.', '', 'settings', '', '', '', False),
    Tab('access', 'سطوح دسترسی حسابدار', 'user-lock', True, 'تعیین کنید حسابدار هر بخش را ببیند یا ویرایش کند.', '', 'settings', '', 'سطوح دسترسی', '', False),
]

# A second menu entry that opens an existing tab with a filter: (tab key, menu label, icon, query, menu group, placed after)
EXTRA_ENTRIES = [('vouchers', 'پیش\u200cنویس سند', 'pen-ruler', 'status=temporary', 'accounting', 'vouchers')]


def menu():
    """What the sidebar and the phone menu draw: ``top`` entries, ``groups`` (each with its entries and sub-headings) and
    ``mobile`` (flat). An entry is ``{key, label, icon, query, heading}``; ``heading`` is set on the first entry of a sub-section."""
    def entry(tab, label=None, icon=None, query='', heading=''):
        return {'key': tab.key, 'label': label or tab.nav_label or tab.label, 'icon': icon or tab.icon, 'query': query, 'heading': heading}

    top = [entry(t) for t in TAB_LIST if not t.group]
    extras = {}
    for key, label, icon, query, group, after in EXTRA_ENTRIES:
        extras.setdefault(after, []).append((label, icon, query))
    groups = []
    for key, label, icon in GROUPS:
        items, section = [], ''
        for tab in (t for t in TAB_LIST if t.group == key):
            heading = tab.section if tab.section != section else ''
            section = tab.section
            items.append(entry(tab, heading=heading))
            for extra_label, extra_icon, query in extras.get(tab.key, ()):
                items.append(entry(tab, label=extra_label, icon=extra_icon, query=query))
        groups.append({'key': key, 'label': label, 'icon': icon, 'items': items})
    mobile = [{'key': t.key, 'label': t.mobile or t.nav_label or t.label, 'icon': t.icon} for t in TAB_LIST if t.mobile is not None]
    return {'top': top, 'groups': groups, 'mobile': mobile}
