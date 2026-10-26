"""Reject dangerous uploads at one choke point.

Only ``main.office.letters`` validated uploads; every other view called
``Model.objects.create(file=request.FILES[...])`` directly, so a user could store
.html/.svg/.exe files that were then served from the site's own origin (stored XSS).
This middleware applies the extension / size / content checks to *every* multipart upload.
"""
import os
import re

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from main.validators import validate_file_content, validate_file_extension, validate_file_size


class UploadValidationMiddleware:
    # Uploads that are only parsed, never stored or served: the accounting backup to restore (a .json.gz the mayor
    # produced). The view checks the role, the envelope and every row itself (main/accounting/backup.py).
    PARSE_ONLY = ('main:acc_p_backup_restore',)

    # The shamim file of a building-permit application may also be a zip / geojson / kml (main/office/permit_form.py checks
    # the extension again). These are stored in the private storage and only ever sent back as a download.
    SHAMIM_EXTENSIONS = ('.zip', '.geojson', '.kml')
    SHAMIM_PATH = re.compile(r'^/(?:services/building-permit/(?:step1/)?|construction-permit/|permits/\d+/supplement/)$')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH') and (request.content_type or '').startswith('multipart/')                 and request.path not in {reverse(name) for name in self.PARSE_ONLY}:
            for uploaded in self._files(request):
                if not uploaded.name:
                    continue
                try:
                    if os.path.splitext(uploaded.name)[1].lower() in self.SHAMIM_EXTENSIONS and self.SHAMIM_PATH.match(request.path):
                        validate_file_size(uploaded)
                        continue
                    validate_file_extension(uploaded)
                    validate_file_size(uploaded)
                    validate_file_content(uploaded)
                except ValidationError as exc:
                    return self._reject(request, '؛ '.join(exc.messages))
        return self.get_response(request)

    @staticmethod
    def _files(request):
        for key in request.FILES:
            yield from request.FILES.getlist(key)

    @staticmethod
    def _reject(request, message):
        wants_json = ('application/json' in request.headers.get('Accept', '')
                      or request.headers.get('X-Requested-With') == 'XMLHttpRequest')
        if wants_json:
            return JsonResponse({'success': False, 'message': message}, status=400)
        back = request.META.get('HTTP_REFERER', '')
        if back and url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            messages.error(request, message)
            return redirect(back)
        return HttpResponse(message, status=400, content_type='text/plain; charset=utf-8')
