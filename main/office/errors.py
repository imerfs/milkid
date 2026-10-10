"""Typed errors; each carries the HTTP status the view answers with."""


class OfficeError(Exception):
    status = 400
    default = 'درخواست نامعتبر است.'

    def __init__(self, message=None):
        super().__init__(message or self.default)


class Invalid(OfficeError):
    status = 400


class Forbidden(OfficeError):
    status = 403
    default = 'شما اجازه‌ی این کار را ندارید.'


class NotFound(OfficeError):
    status = 404
    default = 'مورد درخواستی پیدا نشد.'


class Conflict(OfficeError):
    status = 409
    default = 'این درخواست با وضعیت فعلی هم‌خوانی ندارد.'


class RateLimited(OfficeError):
    status = 429
    default = 'تعداد درخواست‌ها از سقف مجاز گذشته است؛ کمی بعد دوباره تلاش کنید.'
