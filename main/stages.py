"""The stages of the construction-without-a-permit track as one table.

Each stage says what it is called, which state field of the permit file tells where it stands, what that state means for the applicant (``texts``) and in
which states the village staff have something to do (``staff_states``). ``PermitFile.status_text`` and ``PermitFile.needs_staff`` read this table, so a new
step is one row here (plus its step module) instead of a new branch in two model properties.

Stages whose answer depends on several fields at once (3, 4, 5 and 7) name a ``PermitFile`` method in ``custom`` that computes the text and the staff need.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    number: int
    title: str
    state_field: str = ''
    texts: dict = field(default_factory=dict)          # state value -> the line shown in the lists
    staff_states: tuple = ()                           # states in which the clerk / technical expert / dehyari have to act
    staff_always: bool = False                         # the staff act in every state of this stage
    custom: str = ''                                   # 'stepN': the model's step_text / step_needs methods decide
    done_state: str = ''                               # the value of state_field once the stage is finished (used to build a file at a later stage)


UNLICENSED = (
    Stage(1, 'ایجاد پرونده اولیه'),
    Stage(2, 'فرم درخواست و تعهدنامه', 'commission_state',
          {'': 'منتظر فرم درخواست و تعهدنامه‌ی امضاشده (از متقاضی)', 'uploaded': 'فرم درخواست و تعهدنامه منتظر تایید', 'returned': 'فرم‌های امضاشده برگشت خورد'},
          ('uploaded',), done_state='verified'),
    Stage(3, 'اخطاریه و درخواست بازدید', custom='step3'),
    Stage(4, 'گزارش بازدید، پیش‌آمدگی و مصالح', custom='step4'),
    Stage(5, 'معرفی به کارشناس دادگستری و تعهدات', custom='step5'),
    Stage(6, 'پاسخ کارشناس دادگستری و استحکام بنا', 'reply_state',
          {'': 'منتظر دو جوابیه‌ی کارشناس دادگستری (از متقاضی)', 'uploaded': 'جوابیه‌های کارشناس منتظر تایید', 'returned': 'جوابیه‌ها برگشت خورد',
           'verified': 'جوابیه‌ها تایید شد؛ منتظر تایید نهایی مرحله'},
          ('uploaded', 'verified'), done_state='verified'),
    Stage(7, 'پرداخت عوارض و بهای خدمات', custom='step7'),
    Stage(8, 'لیست بازدید بنیاد و نامه‌ی بنیاد', 'bonyad_list_state',
          {'': 'منتظر درخواست قرار گرفتن در لیست بازدید بنیاد (از متقاضی)', 'requested': 'در لیست بازدید بنیاد؛ منتظر تایید انجام بازدید (کارشناس فنی)',
           'released': 'مدارک به متقاضی نشان داده شد؛ منتظر نامه‌ی بنیاد (از متقاضی)', 'uploaded': 'نامه‌ی بنیاد منتظر تایید',
           'returned': 'نامه‌ی بنیاد برگشت خورد', 'verified': 'نامه‌ی بنیاد تایید شد؛ منتظر تایید نهایی مرحله'},
          ('requested', 'uploaded', 'verified'), done_state='verified'),
    Stage(9, 'بسته‌ی فرم‌ها و تعهدنامه‌ی ملک', 'pack_state',
          {'': 'منتظر تعهد مالک و تعهدنامه‌ی ملک (از متقاضی)', 'committed': 'تعهد ثبت شد؛ منتظر تعهدنامه‌ی ملک (از متقاضی)',
           'uploaded': 'تعهدنامه‌ی ملک منتظر تایید', 'returned': 'تعهدنامه‌ی ملک برگشت خورد',
           'verified': 'تعهدنامه‌ی ملک تایید شد؛ منتظر تایید نهایی مرحله'},
          ('uploaded', 'verified'), done_state='verified'),
    Stage(10, 'فرم ۱۶ و امضای بخشدار', 'form16_state',
          {'': 'منتظر فرم ۱۶ و امضای بخشدار (دهیاری)', 'filed': 'فرم ۱۶ امضاشده در پرونده است؛ منتظر تایید نهایی مرحله'}, staff_always=True, done_state='filed'),
    Stage(11, 'خلاصه‌ی پرونده و ارسال به کمیسیون', 'summary_state',
          {'': 'منتظر ارسال خلاصه‌ی پرونده به کمیسیون (دهیاری)', 'sent': 'خلاصه‌ی پرونده به کمیسیون فرستاده شد؛ منتظر تایید نهایی مرحله'}, staff_always=True, done_state='sent'),
    Stage(12, 'رأی کمیسیون، جریمه و پایان کار'),
)
BY_NUMBER = {s.number: s for s in UNLICENSED}
TITLES = [(s.number, s.title) for s in UNLICENSED]
