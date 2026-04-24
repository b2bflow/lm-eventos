from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.permissions import AllowAny
from utils.logger import logger, print_error_details
from events.bus import EventBus
from gateway.interfaces.chat_interface import IChat
from chat.services.message_service import MessageService


class ZApiWebhookController(ViewSet):

    def __init__(self, **kwargs):
        self.client = IChat
        self.message_service = MessageService

    def receive_message(self, request) -> Response:
        try:
            data: dict = request.data or {}
            phone: str = self.client.get_phone(data) or ""

            logger.info(f"[ENDPOINT RECEIVE MESSAGE] Requisição recebida")

            payload: dict = self.message_service.handle(data)

            EventBus.publish_sync("WHATSAPP_MESSAGE_RECEIVED", payload)
            logger.info(f"[ZApiWebhookController] Evento publicado e processado para o telefone: {phone}")

            return Response({"status": "received"}, status=status.HTTP_200_OK)

        except Exception as e:
            print_error_details(e)
            logger.error(f"[ZApiWebhookController] Erro crítico no processamento do webhook: {e}")
            return Response({"detail": "Internal error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)