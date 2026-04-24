from django.apps import AppConfig

class CrmConfig(AppConfig):
    name = 'crm'

    def ready(self):
        try:
            import crm.listeners
        except ImportError:
            pass
