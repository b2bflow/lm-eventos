from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from utils.logger import logger
from analytics.container import AnalyticsContainer

class DashboardController(APIView):
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        try:
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            service = AnalyticsContainer.get_dashboard_service()
            metrics = service.get_general_metrics(start_date=start_date, end_date=end_date)
            return Response(metrics, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[DashboardController] Falha não tratada ao recuperar dashboard: {e}")
            return Response({"detail": "Erro interno do servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)