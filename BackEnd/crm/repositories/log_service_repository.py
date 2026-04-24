from utils.logger import logger
from mongoengine.errors import ValidationError
from crm.models.log_service_model import ServiceLog
from crm.models.custumer_model import Customer
from bson import ObjectId


class ServiceLogRepository:
    
    @classmethod
    def create_log(self, customer: Customer, operator_id: str, action_type: str, description: str) -> ServiceLog:
        try:
            if isinstance(customer, dict):
                customer = Customer.objects(id=ObjectId(customer['id'])).first()

            if not customer:
                raise ValueError("Lead não encontrado para registro de log.")

            log = ServiceLog(
                customer=customer,
                operator_id=str(operator_id) if operator_id else None,
                action_type=action_type,
                description=description,
            )
            log.save()
            return log
        except ValidationError as ve:
            logger.error(f"[ServiceLogRepository] Erro de validação ao salvar log: {ve}")
            raise ValueError("Dados inválidos fornecidos para o log de serviço.")
        except Exception as e:
            logger.error(f"[ServiceLogRepository] Erro interno ao salvar log: {e}")
            raise e

    @classmethod
    def get_by_customer(self, customer_id: str) -> list[ServiceLog]:
        try:
            return ServiceLog.objects.filter(customer=customer_id).order_by('-created_at')
        except Exception as e:
            logger.error(f"[ServiceLogRepository] Erro ao buscar logs do paciente {customer_id}: {e}")
            raise e
