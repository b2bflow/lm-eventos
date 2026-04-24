from django.apps import AppConfig

class ChatConfig(AppConfig):
    name = 'chat'

    def ready(self):
        try:
            import chat.listeners
        except ImportError:
            pass
