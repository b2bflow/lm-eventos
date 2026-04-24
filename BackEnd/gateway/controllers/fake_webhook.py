from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import AllowAny
from utils.logger import logger
from events.bus import EventBus
from gateway.adapters.zapi_adapter import ZAPIClient
from chat.services.message_service import MessageService


class FakeWebhookController(ViewSet):
    permission_classes = [AllowAny]

    permission_classes = [AllowAny]

    def __init__(self, **kwargs):
        self.client = ZAPIClient()
        self.message_service = MessageService()

    def receive_message(self, request) -> Response:
        try:
            data: dict = request.data or {}

            phone: str = self.client.get_phone(**data) or ""

            logger.info(f"[ENDPOINT RECEIVE MESSAGE] Requisição recebida")

            payload: dict = self.message_service.handle(**data)
            if not payload:
                logger.info(f"[FAKE ZApiWebhookController] Mensagem de {phone} ignorada pelas regras de validação.")
                logger.info(f"payload valido: {payload}")
                return Response({"status": "ignored"}, status=status.HTTP_200_OK)

            EventBus.publish_sync("WHATSAPP_MESSAGE_RECEIVED", payload)
            logger.info(f"[FAKE ZApiWebhookController] Evento publicado e processado para o telefone: {phone}")

            return Response({"status": "received"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[FAKE ZApiWebhookController] Erro crítico no processamento do webhook: {e}")
            return Response({"detail": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)