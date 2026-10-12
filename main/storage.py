"""Storage for files that only admins may read (never served by the /media/ location)."""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    @property
    def location(self):
        return os.path.abspath(settings.PRIVATE_MEDIA_ROOT)

    @property
    def base_url(self):
        return None
