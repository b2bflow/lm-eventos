from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Modulos Originais / Mantidos
    path('api/v1/users/', include('users.urls')),
    
    # Novos Modulos do Ecossistema DDD / Eventos
    path('api/v1/crm/', include('crm.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/analytics/', include('analytics.urls')),
    path('api/v1/gateway/', include('gateway.urls')),
]
