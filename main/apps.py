from django.apps import AppConfig


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        from main import audit
        from main.office import permit_request      # pylint: disable=unused-import  (registers the permit guard in main.lifecycle)
        audit.connect()
