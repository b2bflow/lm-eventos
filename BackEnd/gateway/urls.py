from django.urls import path
from gateway.controllers.fake_webhook import FakeWebhookController
from gateway.controllers.webhook_controller import ZApiWebhookController
from gateway.controllers.zapi_connection_controller import ZapiDisconnectController, ZapiStatusController

urlpatterns = [
    path('webhook/zapi/', FakeWebhookController.as_view({'post': 'receive_message'}), name='zapi_webhook'),
    path('zapi/status/', ZapiStatusController.as_view(), name='zapi_status'),
    path('zapi/disconnect/', ZapiDisconnectController.as_view(), name='zapi_disconnect'),
]
