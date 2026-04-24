from database.client.mongodb_client import MongoDBClient
from utils.logger import logger
from typing import List, Any, Optional
from datetime import datetime
from crm.interfaces.customer_service_interface import ICustomerService
from crm.repositories.customer_repository import CustomerRepository
from crm.repositories.log_service_repository import ServiceLogRepository


class CustomerService(ICustomerService):
    MANUAL_STAGES = {'WON', 'LOST'}
    INTERACTION_FIELDS = {'notes', 'last_interaction_at', 'next_step'}

    def __init__(self):
        self.customer_repo = CustomerRepository(MongoDBClient())

    def _parse_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            cleaned = value.replace('Z', '+00:00')
            try:
                return datetime.fromisoformat(cleaned)
            except ValueError:
                for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue
        raise ValueError("Data inválida informada.")

    def _normalize_status_aliases(self, data: dict) -> dict:
        if 'actual_status' in data and 'customer_state_now' not in data:
            data['customer_state_now'] = data.pop('actual_status')
        return data

    def _normalize_phone_data(self, data: dict) -> dict:
        """Centraliza o tratamento de chaves divergentes entre Front e DB"""
        if 'cel_number' in data and 'phone' not in data:
            data['phone'] = data.pop('cel_number')
        return data

    def _normalize_event_data(self, data: dict) -> dict:
        numeric_fields = {'guest_count': int, 'quoted_amount': float, 'contract_value': float}
        datetime_fields = {'event_date', 'proposal_sent_at', 'last_interaction_at'}

        for field, caster in numeric_fields.items():
            if field in data and data[field] not in (None, ''):
                data[field] = caster(data[field])

        for field in datetime_fields:
            if field in data:
                data[field] = self._parse_datetime(data[field]) if data[field] else None

        return data

    def _infer_stage(self, existing_customer: Optional[dict], payload: dict) -> str:
        requested_stage = payload.get('customer_state_now')
        current_stage = existing_customer.get('customer_state_now') if existing_customer else None

        if requested_stage in self.MANUAL_STAGES:
            return requested_stage

        if current_stage in self.MANUAL_STAGES and requested_stage not in self.MANUAL_STAGES:
            return current_stage

        quoted_amount = payload.get('quoted_amount')
        if quoted_amount is None and existing_customer:
            quoted_amount = existing_customer.get('quoted_amount')

        contract_value = payload.get('contract_value')
        if contract_value is None and existing_customer:
            contract_value = existing_customer.get('contract_value')

        proposal_sent_at = payload.get('proposal_sent_at')
        if proposal_sent_at is None and existing_customer:
            proposal_sent_at = existing_customer.get('proposal_sent_at')

        has_budget = any(value not in (None, '', 0, 0.0) for value in [quoted_amount, contract_value]) or bool(proposal_sent_at)
        has_interaction = any(payload.get(field) not in (None, '') for field in self.INTERACTION_FIELDS)

        if has_budget and has_interaction:
            return 'NEGOTIATING'
        if has_budget:
            return 'BUDGET'
        return 'ANALYSIS'

    def _build_log_payload(self, existing_customer: Optional[dict], updated_payload: dict, resolved_stage: str) -> Optional[dict]:
        previous_stage = existing_customer.get('customer_state_now') if existing_customer else None

        if resolved_stage in self.MANUAL_STAGES and previous_stage != resolved_stage:
            label = 'Venda fechada' if resolved_stage == 'WON' else 'Oportunidade perdida'
            return {'action_type': 'STAGE_CHANGED', 'description': label}

        if resolved_stage == 'NEGOTIATING':
            return {'action_type': 'NEGOTIATION_INTERACTION', 'description': 'Interação registrada após envio do orçamento.'}

        quote_keys = {'quoted_amount', 'contract_value', 'proposal_sent_at'}
        if resolved_stage == 'BUDGET' and any(key in updated_payload for key in quote_keys):
            return {'action_type': 'BUDGET_SENT', 'description': 'Orçamento gerado ou atualizado para o lead.'}

        if previous_stage and previous_stage != resolved_stage:
            return {'action_type': 'STAGE_CHANGED', 'description': f'Etapa alterada para {resolved_stage}.'}

        return {'action_type': 'LEAD_UPDATED', 'description': 'Dados comerciais do lead atualizados.'}

    def register_customer(self, data: dict, user: Any = None) -> Any:
        try:
            data = self._normalize_status_aliases(data)
            data = self._normalize_phone_data(data)
            data = self._normalize_event_data(data)
            name = data.get('name')
            phone = data.get('phone')
            
            if not phone:
                raise ValueError("O número de telefone é obrigatório.")

            data['customer_state_now'] = self._infer_stage(existing_customer=None, payload=data)
            customer = self.customer_repo.create(
                name=name,
                phone=phone,
                agent="response_orchestrator",
            )
            customer = self.customer_repo.update(id=customer['id'], attributes={
                **data,
                'updated_at': datetime.utcnow(),
            })
            
            operator_id = str(user.id) if user and hasattr(user, 'id') else None
            ServiceLogRepository.create_log(
                customer=customer,
                operator_id=operator_id,
                action_type='LEAD_CREATED', 
                description=f"Lead registado via {data.get('source', 'Sistema')}"
            )
            
            return customer
        except Exception as e:
            logger.error(f"[CustomerService] Erro ao registar lead: {str(e)}")
            raise e

    def get_active_customers(self, status_filter: Optional[str] = None, search_term: Optional[str] = None) -> List[Any]:
        try:
            return self.customer_repo.get_all_customers(status_filter=status_filter, search_term=search_term)
        except Exception as e:
            logger.error(f"[CustomerService] Erro ao listar leads: {str(e)}")
            return []

    def update_customer_info(self, customer_id: str, data: dict, user: Any = None) -> Any:
        try:
            data = self._normalize_status_aliases(data)
            data = self._normalize_phone_data(data)
            data = self._normalize_event_data(data)

            existing_customer = self.customer_repo.get_by_id(customer_id)
            if not existing_customer:
                raise ValueError("Lead não encontrado.")

            data['customer_state_now'] = self._infer_stage(existing_customer=existing_customer, payload=data)
            data['updated_at'] = datetime.utcnow()
            customer = self.customer_repo.update(id=customer_id, attributes=data)
            if not customer:
                raise ValueError("Lead não encontrado.")

            operator_id = str(user.id) if user and hasattr(user, 'id') else None
            log_payload = self._build_log_payload(existing_customer, data, customer['customer_state_now'])
            ServiceLogRepository.create_log(
                customer=customer,
                operator_id=operator_id,
                action_type=log_payload['action_type'],
                description=log_payload['description']
            )
            
            logger.info(f"[CustomerService] Dados do lead {customer_id} atualizados.")
            return customer
        except Exception as e:
            logger.error(f"[CustomerService] Falha na atualização do lead {customer_id}: {str(e)}")
            raise e
            
    def get_customer_name_by_id(self, customer_id: str) -> str:
        try:
            customer = self.customer_repo.get_by_id(customer_id)
            return customer.get('name') if customer else "Lead Desconhecido"
        except Exception:
            return "Erro ao buscar nome"

    def get_customer_by_phone(self, phone: str) -> Any:
        try:
            return self.customer_repo.get_by_phone(phone)
        except Exception as e:
            logger.error(f"[CustomerService] Erro ao buscar lead por telefone: {str(e)}")
            return None
        
    def delete_customer(self, customer_id: str, user: Any = None) -> bool:
        try:
            customer = self.customer_repo.get_by_id(customer_id)
            if customer:
                operator_id = str(user.id) if user and hasattr(user, 'id') else None
                ServiceLogRepository.create_log(
                    customer=customer,
                    operator_id=operator_id,
                    action_type='LEAD_DELETED', 
                    description="Lead excluído do sistema."
                )
            return self.customer_repo.delete_customer(customer_id)
        except Exception as e:
            logger.error(f"[CustomerService] Erro ao deletar lead: {str(e)}")
            raise e
