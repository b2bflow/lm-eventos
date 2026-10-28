from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import AllowAny
from utils.logger import logger
from events.bus import EventBus
from gateway.adapters.zapi_adapter import ZAPIClient
from gateway.service.webhook_guard_service import WebhookGuardService
from chat.services.message_service import MessageService
from chat.services.phone_sent_message_service import PhoneSentMessageService


class FakeWebhookController(ViewSet):
    # Autenticação é o token do webhook (WebhookGuardService), não JWT.
    permission_classes = [AllowAny]
    authentication_classes = []
    # A Z-API envia de poucos IPs: o throttle anônimo global (10/min) derrubaria mensagens.
    throttle_classes = []

    guard = WebhookGuardService()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = ZAPIClient()
        self.message_service = MessageService()
        self.phone_sent = PhoneSentMessageService(self.client)

    def receive_message(self, request) -> Response:
        if not self.guard.is_authorized(request):
            logger.warning("[ZApiWebhook] Requisição recusada: token do webhook ausente ou inválido.")
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            data: dict = request.data or {}

            phone: str = self.client.get_phone(**data) or ""

            logger.info(f"[ENDPOINT RECEIVE MESSAGE] Requisição recebida")

            if self.guard.is_duplicate(data):
                logger.info(f"[ZApiWebhook] Mensagem repetida de {phone} ignorada.")
                return Response({"status": "duplicate"}, status=status.HTTP_200_OK)

            # Enviada pela equipe direto no WhatsApp (celular/Web): registra e tira a IA da conversa.
            if self.phone_sent.matches(data):
                self.phone_sent.process(data)
                return Response({"status": "received"}, status=status.HTTP_200_OK)

            payload: dict = self.message_service.handle(**data)
            if not payload:
                logger.info(f"[FAKE ZApiWebhookController] Mensagem de {phone} ignorada pelas regras de validação.")
                return Response({"status": "ignored"}, status=status.HTTP_200_OK)

            EventBus.publish_sync("WHATSAPP_MESSAGE_RECEIVED", payload)
            logger.info(f"[FAKE ZApiWebhookController] Evento publicado e processado para o telefone: {phone}")

            return Response({"status": "received"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[FAKE ZApiWebhookController] Erro crítico no processamento do webhook: {e}")
            return Response({"detail": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
