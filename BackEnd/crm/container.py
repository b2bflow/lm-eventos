from utils.logger import logger
from crm.services.customer_service import CustomerService
from crm.interfaces.customer_service_interface import ICustomerService
from crm.services.log_service import LogService
from crm.interfaces.log_service_interface import ILogService
from crm.services.quote_service import QuoteService


class CrmContainer:
    _customer_service = None
    _log_service = None
    _quote_service = None
    _pipeline_service = None
    _sdr_task_service = None
    _lead_qualification_service = None
    _notification_service = None
    _contact_service = None

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

    @classmethod
    def get_quote_service(self) -> QuoteService:
        try:
            if not self._quote_service:
                self._quote_service = QuoteService()
                logger.info("[CrmContainer] QuoteService instanciado via Container.")
            return self._quote_service
        except Exception as e:
            logger.error(f"[CrmContainer] Erro ao instanciar QuoteService: {e}")
            raise e

    @classmethod
    def get_pipeline_service(cls):
        if not cls._pipeline_service:
            from crm.services.pipeline_service import PipelineService
            cls._pipeline_service = PipelineService()
        return cls._pipeline_service

    @classmethod
    def get_sdr_task_service(cls):
        if not cls._sdr_task_service:
            from crm.services.sdr_task_service import SdrTaskService
            cls._sdr_task_service = SdrTaskService()
        return cls._sdr_task_service

    @classmethod
    def get_notification_service(cls):
        if not cls._notification_service:
            from crm.services.notification_service import NotificationService
            cls._notification_service = NotificationService()
        return cls._notification_service

    @classmethod
    def get_lead_qualification_service(cls):
        """Serviço que a IA vai chamar a partir das functions (ver crm/README.md)."""
        if not cls._lead_qualification_service:
            from crm.services.lead_qualification_service import LeadQualificationService
            cls._lead_qualification_service = LeadQualificationService()
        return cls._lead_qualification_service

    @classmethod
    def get_contact_service(cls):
        """Contatos e histórico de leads (página Contatos, importação de parceiros)."""
        if not cls._contact_service:
            from crm.services.contact_service import ContactService
            cls._contact_service = ContactService()
        return cls._contact_service
