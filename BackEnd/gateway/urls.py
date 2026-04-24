from django.urls import path
from gateway.controllers.fake_webhook import FakeWebhookController
from gateway.controllers.webhook_controller import ZApiWebhookController

urlpatterns = [
    path('webhook/zapi/', FakeWebhookController.as_view({'post': 'receive_message'}), name='zapi_webhook'),
]