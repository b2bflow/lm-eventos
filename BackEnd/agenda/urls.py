from django.urls import path

from agenda.controllers import (
    EventDetailController, EventsController, GoogleCallbackController, GoogleConnectController, GoogleStatusController,
    GoogleSyncController,
)

urlpatterns = [
    path('events/', EventsController.as_view(), name='agenda-events'),
    path('events/<str:event_id>/', EventDetailController.as_view(), name='agenda-event'),
    path('google/status/', GoogleStatusController.as_view(), name='agenda-google-status'),
    path('google/connect/', GoogleConnectController.as_view(), name='agenda-google-connect'),
    path('google/callback/', GoogleCallbackController.as_view(), name='agenda-google-callback'),
    path('google/sync/', GoogleSyncController.as_view(), name='agenda-google-sync'),
]
