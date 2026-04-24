from utils.logger import logger
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from chat.services.system_config_service import SystemConfigService
from chat.serializers import SystemConfigDTO


class SystemConfigController(viewsets.ViewSet):
    permission_classes = [permissions.IsAdminUser]

    def list(self, request):
        try:
            config = SystemConfigService.get_configuration()
            serializer = SystemConfigDTO(config)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[SystemConfigController] Erro GET: {str(e)}")
            return Response({"detail": "Erro ao buscar configurações."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request):
        try:
            config = SystemConfigService.update_configuration(request.data)
            serializer = SystemConfigDTO(config)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[SystemConfigController] Erro UPDATE: {str(e)}")
            return Response({"detail": "Erro ao salvar configurações."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)