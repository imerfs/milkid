"""What the master plan's legend and notes say about each easement (حریم).

The text comes from the plan itself (its legacy Persian font is decoded by scripts/gis/shx_text.py); the distances are
the plan's own. Two things are inferred, not written in the plan: the generic ``general`` easement (drawn on the layer
named ``Harim``) has no note of its own, and the two defence zones are told apart by size: the layer ``harim padafand 1``
covers 3 ha and ``harim padafand 2`` 12 ha, so they are taken as the 50 m and the 150 m zones.
"""

EASEMENT_INFO = {
    'general': ('حریم', ''),
    'quality': ('حریم کیفی مسیل', 'هرگونه ساخت‌وساز و تغییر وضعیت طبیعی زمین در حریم کیفی مسیل ممنوع می‌باشد.'),
    'qanat': ('حریم کمی قنات', 'رعایت حریم کمی قنات به میزان ۶ متر الزامی می‌باشد.'),
    'qanat_quality': (
        'حریم کیفی قنات',
        'در محدوده‌ی حریم کیفی قنوات از احداث هرگونه واحد آلاینده، تغییر کاربری و حفر هرگونه چاه جذبی، تخلیه‌ی پساب، '
        'دفن و دپوی پسماند و زهکشی اراضی کشاورزی خودداری گردد.'),
    'defense1': ('حریم ۵۰ متر پدافند', 'با محدودیت ساخت ۲ طبقه روی پیلوت.'),
    'defense2': ('حریم ۱۵۰ متر پدافند', 'با محدودیت ساخت ۳ طبقه روی پیلوت.'),
}


def label(kind):
    return EASEMENT_INFO.get(kind, (kind, ''))[0]


def rule(kind):
    return EASEMENT_INFO.get(kind, ('', ''))[1]
