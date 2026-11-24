from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from gateway.service.zapi_connection_service import ZapiConnectionError, ZapiConnectionService
from users.permissions import IsAdminRole
from utils.logger import logger


class ZapiStatusController(APIView):
    """GET /gateway/zapi/status/ (só admin): conexão do WhatsApp da LM na Z-API.

    ?qr=1 traz o QR Code quando está desconectado (a tela pede a cada 15 s enquanto a pessoa conecta:
    o WhatsApp troca o código a cada ~20 s).
    """
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        with_qr = str(request.query_params.get("qr", "")).lower() in ("1", "true", "sim")
        return Response(ZapiConnectionService().status(with_qr=with_qr))


class ZapiDisconnectController(APIView):
    """POST /gateway/zapi/disconnect/ (só admin): desconecta o WhatsApp da instância. A IA e o painel
    param de receber e enviar mensagens até alguém conectar de novo pelo QR Code."""
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        try:
            snapshot = ZapiConnectionService().disconnect()
        except ZapiConnectionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        logger.warning(f"[ZapiConnection] WhatsApp desconectado por {request.user.username}.")
        return Response(snapshot)
