import os
from database.client.mongodb_client import MongoDBClient
from utils.logger import logger
from typing import List, Any, Optional
from datetime import datetime
from crm.interfaces.customer_service_interface import ICustomerService
from crm.repositories.customer_repository import CustomerRepository
from crm.repositories.log_service_repository import ServiceLogRepository
from chat.models.conversation_model import ConversationModel
from gateway.adapters.zapi_adapter import ZAPIClient
from crm import domain
from crm.phones import normalize_phone

# Campos que o cadastro e a edição pela visão em tabela (/leads) gravam. O resto do lead tem regra
# própria: sinalizações, anexos, qualificação e operador humano têm endpoints do card; datas de
# proposta, qualificação e primeiro contato são gravadas pelos fluxos que as originam.
FORM_FIELDS = frozenset([
    "name", "phone", "celebration_type", "event_title", "event_date", "guest_count", "quoted_amount",
    "contract_value", "venue", "notes", "next_step", "last_interaction_at", "customer_custom_tag",
    "email", "company", "role", "contact_type", "origin", "owner", "product",
])

FORM_CHOICES = {
    "contact_type": domain.CONTACT_TYPES, "origin": domain.ORIGINS, "owner": domain.OWNERS,
    "product": domain.PRODUCTS,
}


class CustomerService(ICustomerService):
    """Cadastro e edição do lead. Mudança de etapa é explícita (PipelineService.change_stage)."""

    def __init__(self):
        self.customer_repo = CustomerRepository(MongoDBClient())
        self.zapi_client = ZAPIClient()

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
        datetime_fields = {'event_date', 'proposal_sent_at', 'last_interaction_at', 'next_action_at'}

        for field, caster in numeric_fields.items():
            if field in data and data[field] not in (None, ''):
                data[field] = caster(data[field])

        for field in datetime_fields:
            if field in data:
                data[field] = self._parse_datetime(data[field]) if data[field] else None

        return data

    def _form_data(self, data: dict) -> dict:
        """Só os campos do formulário, com listas de valores conferidas e vazio virando None."""
        cleaned = {}
        for key in FORM_FIELDS:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, str):
                value = value.strip()
            if key in FORM_CHOICES:
                if value in (None, ''):
                    value = None if key in ('origin', 'product') else ('lead' if key == 'contact_type' else 'sdr')
                elif value not in FORM_CHOICES[key]:
                    raise ValueError(f"Valor inválido para {key}: {value}.")
            elif value == '' and key not in ('name',):
                value = None
            cleaned[key] = value
        return cleaned

    def _form_phone(self, raw, current_id: str | None = None) -> str:
        """Telefone do formulário com DDI e sem duplicar contato (mesma regra da página Contatos)."""
        from crm.services.contact_service import DuplicateContactError, find_by_phone
        phone = normalize_phone(raw)
        if not phone:
            raise ValueError("Telefone inválido. Use DDD e número, por exemplo (62) 99999-1111.")
        existing = find_by_phone(phone)
        if existing and str(existing.id) != str(current_id):
            raise DuplicateContactError(existing)
        return phone

    def _has_budget_payload(self, data: dict) -> bool:
        quoted_amount = data.get('quoted_amount')
        contract_value = data.get('contract_value')
        return any(value not in (None, '', 0, 0.0) for value in [quoted_amount, contract_value])

    def _build_financial_summary(self, customer: dict) -> str:
        def value_or_dash(value):
            return value if value not in (None, '') else '-'

        amount = customer.get('quoted_amount') or customer.get('contract_value') or 0
        lines = [
            "*Orçamento definido*",
            f"Cliente: {value_or_dash(customer.get('name'))}",
            f"Telefone: {value_or_dash(customer.get('phone'))}",
            f"Valor: R$ {float(amount or 0):,.2f}",
            f"Evento/Produto: {value_or_dash(customer.get('event_title') or customer.get('celebration_type'))}",
            f"Local: {value_or_dash(customer.get('venue'))}",
            f"Resumo: {value_or_dash(customer.get('notes'))}",
            f"Próximo passo: {value_or_dash(customer.get('next_step'))}",
        ]
        return "\n".join(lines)

    def _mark_budget_and_notify_finance(self, customer: dict) -> None:
        try:
            conversation = ConversationModel.objects(customer=customer.get('id'), status__in=['OPEN', 'IN_PROGRESS']).first()
            if conversation:
                conversation.tag = 'orcamento'
                conversation.ai_active = False
                conversation.needs_attention = True
                conversation.save()

            finance_phone = (
                os.getenv("FINANCE_PHONE")
                or os.getenv("FINANCEIRO_PHONE")
                or os.getenv("ADM_PHONE")
                or os.getenv("REGISTER_PHONE")
                or ""
            ).strip()

            if not finance_phone:
                logger.warning("[CustomerService] FINANCE_PHONE não configurado. Resumo financeiro não enviado.")
                return

            self.zapi_client.send_message(
                phone=finance_phone,
                message=self._build_financial_summary(customer),
            )
        except Exception as e:
            logger.error(f"[CustomerService] Falha ao notificar financeiro: {str(e)}")

    def register_customer(self, data: dict, user: Any = None, from_form: bool = False) -> Any:
        """Cria o contato com o lead em NEW_LEAD (a etapa só muda pelas transições do funil).

        `from_form=True` (cadastro pela tela): aceita só os campos do formulário, normaliza o
        telefone e recusa número já cadastrado. O webhook chama sem `from_form`, com o telefone
        exatamente como a Z-API manda.
        """
        try:
            data = self._normalize_status_aliases(data)
            data = self._normalize_phone_data(data)
            if from_form:
                data = self._form_data(data)
                data['phone'] = self._form_phone(data.get('phone'))
            data = self._normalize_event_data(data)
            name = data.get('name')
            phone = data.get('phone')
            
            if not phone:
                raise ValueError("O número de telefone é obrigatório.")

            data['customer_state_now'] = domain.NEW_LEAD
            data['stage_changed_at'] = datetime.utcnow()
            customer = self.customer_repo.create(
                name=name,
                phone=phone,
                agent="response_orchestrator",
            )
            name_collected = True if user else False
            customer = self.customer_repo.update(id=customer['id'], attributes={
                **data,
                'name_collected': name_collected,
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

    def get_active_customers(
        self,
        status_filter: Optional[str] = None,
        search_term: Optional[str] = None,
        custom_tag_filter: Optional[str] = None,
    ) -> List[Any]:
        try:
            return self.customer_repo.get_all_customers(
                status_filter=status_filter,
                search_term=search_term,
                custom_tag_filter=custom_tag_filter,
            )
        except Exception as e:
            logger.error(f"[CustomerService] Erro ao listar leads: {str(e)}")
            return []

    def page_customers(self, status_filter: Optional[str] = None, search_term: Optional[str] = None,
                       offset: int = 0, limit: int = 10, custom_tag_filter: Optional[str] = None) -> tuple[list, int]:
        """Página de leads paginada no banco (visão em tabela /leads)."""
        return self.customer_repo.page_customers(status_filter=status_filter, search_term=search_term, offset=offset, limit=limit, custom_tag_filter=custom_tag_filter)

    def update_customer_info(self, customer_id: str, data: dict, user: Any = None) -> Any:
        try:
            data = self._normalize_status_aliases(data)
            data = self._normalize_phone_data(data)
            requested_stage = data.get('customer_state_now') or None
            lost_reason = data.get('lost_reason') or None
            data = self._form_data(data)

            existing_customer = self.customer_repo.get_by_id(customer_id)
            if not existing_customer:
                raise ValueError("Lead não encontrado.")
            if 'phone' in data:
                data['phone'] = self._form_phone(data['phone'], current_id=customer_id)
            data = self._normalize_event_data(data)

            from crm.container import CrmContainer
            pipeline = CrmContainer.get_pipeline_service()
            stage_changed = bool(requested_stage) and requested_stage != existing_customer['customer_state_now']
            if stage_changed:
                # Valida antes de gravar qualquer campo, para não salvar a edição pela metade.
                pipeline.validate_transition(existing_customer, requested_stage, user, lost_reason)

            data['updated_at'] = datetime.utcnow()
            customer = self.customer_repo.update(id=customer_id, attributes=data)
            if not customer:
                raise ValueError("Lead não encontrado.")

            if self._has_budget_payload(data):
                self.customer_repo.update(
                    id=customer_id,
                    attributes={"customer_custom_tag": "orcamento"},
                )
                customer["customer_custom_tag"] = "orcamento"
                self._mark_budget_and_notify_finance(customer)

            operator_id = str(user.id) if user and hasattr(user, 'id') else None
            ServiceLogRepository.create_log(
                customer=customer,
                operator_id=operator_id,
                action_type='LEAD_UPDATED',
                description='Dados comerciais do lead atualizados.'
            )

            # Etapa só muda pela transição explícita (valida e registra na linha do tempo).
            if stage_changed:
                customer = pipeline.change_stage(customer_id, requested_stage, user=user, lost_reason=lost_reason)

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

    def get_customer_needs_follow_up(self) -> List[dict]:
        
        try:
            return self.customer_repo.get_customers_needing_follow_up()

        except Exception:
            logger.exception(
                "[CustomerService] Erro ao buscar clientes para follow-up"
            )
            return []
        
    FOLLOW_UP_TEMPLATE = (
        "Olá{customer_name}! Eu sou a Lins.\n\n"
        "Percebi que nossa conversa ficou parada e gostaria de saber "
        "se ainda posso ajudar você com alguma informação ou dúvida.\n\n"
        "Fico à disposição!"
    )

    def _build_follow_up_message(self, customer: dict) -> str:
        name = customer.get("name")

        customer_name = f", {name}" if name else ""

        return self.FOLLOW_UP_TEMPLATE.format(
            customer_name=customer_name
        )

    def _send_follow_up_message(self, customer: dict) -> bool:
        customer_id = customer.get("id")
        phone = customer.get("phone")

        if not customer_id:
            logger.warning(
                "[CustomerService] Cliente sem id. Follow-up cancelado."
            )
            return False

        if not phone:
            logger.warning(
                f"[CustomerService] Cliente {customer_id} sem telefone. "
                "Follow-up cancelado."
            )
            return False

        try:
            message = self._build_follow_up_message(customer)

            self.zapi_client.send_message(
                phone=phone,
                message=message,
            )

            self.customer_repo.update(
                id=customer_id,
                attributes={
                    "followup_sent": True,
                    "updated_at": datetime.now(),
                    "agent": "follow_up_agent",
                    "send_button": False,
                    # "new_service": False,
                },
            )

            logger.info(
                f"[CustomerService] Follow-up enviado para cliente {customer_id}"
            )

            return True

        except Exception:
            logger.exception(
                f"[CustomerService] Erro ao enviar follow-up para cliente {customer_id}"
            )
            return False
        
    def process_follow_ups(self) -> None:
        customers = self.get_customer_needs_follow_up()

        logger.info(
            f"[CustomerService] {len(customers)} clientes encontrados para follow-up"
        )

        for customer in customers:
            self._send_follow_up_message(customer)
