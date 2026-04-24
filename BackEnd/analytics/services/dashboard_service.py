from typing import Dict, Any, Optional
from utils.logger import logger
from analytics.interfaces.dashboard_service_interface import IDashboardService
from analytics.read_models.dashboard_repository import DashboardRepository

class DashboardService(IDashboardService):
    def get_general_metrics(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        try:
            metrics = DashboardRepository.get_metrics(start_date=start_date, end_date=end_date)
            logger.info("[DashboardService] Métricas dinâmicas resgatadas com sucesso.")
            return metrics
        except Exception as e:
            logger.error(f"[DashboardService] Erro crítico ao buscar métricas: {e}")
            raise e