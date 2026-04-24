from django.apps import AppConfig

class AnalyticsConfig(AppConfig):
    name = 'analytics'

    def ready(self):
        try:
            import analytics.listeners
        except ImportError:
            pass
