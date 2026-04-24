from utils.logger import logger
from crm.services.customer_service import CustomerService
from crm.interfaces.customer_service_interface import ICustomerService
from crm.services.log_service import LogService
from crm.interfaces.log_service_interface import ILogService


class CrmContainer:
    _customer_service = None
    _log_service = None

    @classmethod
    def get_customer_service(self) -> ICustomerService:
        try:
            if not self._customer_service:
                self._customer_service = CustomerService()
                logger.info("[CrmContainer] CustomerService instanciado via Container.")
            return self._customer_service
        except Exception as e:
            logger.error(f"[CrmContainer] Erro ao instanciar CustomerService: {e}")
            raise e

    @classmethod
    def get_log_service(self) -> ILogService:
        try:
            if not self._log_service:
                self._log_service = LogService()
                logger.info("[CrmContainer] LogService instanciado via Container.")
            return self._log_service
        except Exception as e:
            logger.error(f"[CrmContainer] Erro ao instanciar LogService: {e}")
            raise e

