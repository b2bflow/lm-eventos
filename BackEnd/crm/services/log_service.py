from typing import List, Any
from utils.logger import logger
from crm.interfaces.log_service_interface import ILogService
from crm.repositories.log_service_repository import ServiceLogRepository
from crm.repositories.customer_repository import CustomerRepository


class LogService(ILogService):
    def create_log(self, customer_id: str, operator_id: str, action_type: str, description: str) -> Any:
        try:
            if not customer_id:
                raise ValueError("O ID do paciente é obrigatório para registrar um log.")
            
            customer = CustomerRepository.get_by_id(customer_id)
            if not customer:
                raise ValueError(f"Paciente com ID {customer_id} não encontrado.")

            log = ServiceLogRepository.create_log(
                customer=customer,
                operator_id=operator_id,
                action_type=action_type,
                description=description
            )
            
            logger.info(f"[LogService] Log registrado para o paciente {customer_id} (Ação: {action_type}).")
            return log

        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"[LogService] Erro ao criar log de serviço: {e}")
            raise e

    def get_customer_logs(self, customer_id: str) -> List[Any]:
        try:
            if not customer_id:
                raise ValueError("O ID do paciente é obrigatório para buscar logs.")
            return ServiceLogRepository.get_by_customer(customer_id)
        except ValueError as ve:
            raise ve
        except Exception as e:
            logger.error(f"[LogService] Erro ao buscar logs: {e}")
            raise e