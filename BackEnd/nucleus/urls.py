from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from agenda.controllers import GoogleCallbackController

urlpatterns = [
    # Retorno do Google no endereço já cadastrado no client OAuth "LM B2B Flow" (domínio oauth.b2bflow.com.br).
    path('auth/google/callback', GoogleCallbackController.as_view(), name='google-oauth-callback'),

    # Modulos Originais / Mantidos
    path('api/v1/users/', include('users.urls')),
    
    # Novos Modulos do Ecossistema DDD / Eventos
    path('api/v1/crm/', include('crm.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/analytics/', include('analytics.urls')),
    path('api/v1/gateway/', include('gateway.urls')),
    path('api/v1/sales/', include('sales.urls')),
    path('api/v1/inventory/', include('inventory.urls')),
    path('api/v1/agenda/', include('agenda.urls')),
]

if settings.DJANGO_ADMIN_ENABLED:
    urlpatterns.append(path('admin/', admin.site.urls))
