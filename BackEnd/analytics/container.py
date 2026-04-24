from utils.logger import logger
from analytics.services.dashboard_service import DashboardService
from analytics.interfaces.dashboard_service_interface import IDashboardService

class AnalyticsContainer:
    _dashboard_service = None

    @classmethod
    def get_dashboard_service(self) -> IDashboardService:
        try:
            if not self._dashboard_service:
                self._dashboard_service = DashboardService()
                logger.info("DashboardService instanciado via Container.")
            return self._dashboard_service
        except Exception as e:
            logger.error(f"Erro ao instanciar DashboardService: {e}")
            raise e
