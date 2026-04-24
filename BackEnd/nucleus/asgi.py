import os
import socketio
from django.core.asgi import get_asgi_application
from .sio import sio 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nucleus.settings')

django_asgi_app = get_asgi_application()

application = socketio.ASGIApp(sio, django_asgi_app)