from chat.models.conversation_model import ConversationModel
from chat.repositories.system_config_repository import SystemConfigRepository
from crm.models.custumer_model import Customer
from mongoengine.errors import DoesNotExist
from chat.interfaces.conversation_repository_interface import IConversationRepository
from utils.logger import logger
from datetime import datetime
from mongoengine.queryset.visitor import Q
import re

# Etiquetas de atendimento humano: a plataforma grava OPERADOR; a IA, ao transferir, grava as outras.
OPERATOR_TAGS = ['OPERADOR', 'operador_humano', 'operador humano', 'orcamento']


class ConversationRepository(IConversationRepository):
    @staticmethod
    def get_by_id(conversation_id: str) -> ConversationModel | None:
        try:
            return ConversationModel.objects.get(id=conversation_id)
        except DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao buscar conversa por ID: {e}")
            raise e

    @staticmethod
    def get_active_conversation(customer: Customer) -> ConversationModel | None:
        try:
            conversation = ConversationModel.objects(
                customer=customer,
                status__in=['OPEN', 'IN_PROGRESS']
            ).first()

            return conversation

        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao buscar conversa ativa: {e}")
            raise e

    @staticmethod
    def create_conversation(customer) -> ConversationModel: # Removi a tipagem rígida de Customer aqui para evitar avisos da IDE
        try:

            conv = ConversationModel(
                customer=customer,
                status='OPEN',
                tag='AGENTE',
                ai_active=True,
            )
            conv.save()

            # Ajuste aqui: Se 'customer' for string, usa ela direto. Se for objeto, pega o .id
            customer_id = customer if isinstance(customer, str) else str(getattr(customer, 'id', customer))

            # Conversa nova atendida pela IA: o contato entra no funil (ver crm.services.funnel_entry)
            from crm.services.funnel_entry import enter_funnel
            enter_funnel(customer_id, only_eligible=True)

            logger.info(f"[ConversationRepository] Nova conversa iniciada para o Paciente {customer_id}. Tag definida como: {conv.tag}")
            return conv

        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao criar conversa: {e}")
            raise e

    @staticmethod
    def update_conversation(conversation: ConversationModel):
        try:
            conversation.updated_at = datetime.utcnow()
            conversation.save()
            return conversation
        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao atualizar conversa {conversation.id}: {e}")
            raise e

    @staticmethod
    def get_all_ordered_by_interaction():
        try:
            return ConversationModel.objects.all().order_by('-updated_at')
        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao listar conversas: {e}")
            raise e

    @staticmethod
    def filtered_queryset(search: str | None = None, tag: str | None = None, needs_attention: bool | None = None, status: str | None = None,
                          assignee: str | None = None, ai_qualified: bool | None = None):
        """Conversas filtradas no banco: busca por nome ou telefone do cliente, etiqueta, atenção e situação.

        status: OPEN (abertas) ou CLOSED (fechadas e arquivadas).
        tag: AGENTE (IA atendendo) ou OPERADOR (inclui as variações gravadas pela IA ao transferir).
        ai_qualified: só conversas de leads qualificados pela IA (Customer.ai_qualified_at).
        """
        from mongoengine.queryset.visitor import Q
        queryset = ConversationModel.objects.all()
        if status == 'OPEN':
            queryset = queryset.filter(status__nin=['CLOSED', 'ARCHIVED'])
        elif status == 'CLOSED':
            queryset = queryset.filter(status__in=['CLOSED', 'ARCHIVED'])
        if search:
            term = search.strip()
            digits = "".join(ch for ch in term if ch.isdigit())
            customer_filter = Q(name__icontains=term)
            # Telefone só quando o termo não tem letras (ex.: "(62) 99999-0000"), para "Cliente 01" não casar números.
            if digits and not any(ch.isalpha() for ch in term):
                customer_filter = customer_filter | Q(phone__icontains=digits)
            customer_ids = [c.id for c in Customer.objects(customer_filter).only('id')]
            queryset = queryset.filter(customer__in=customer_ids)
        if tag == 'OPERADOR':
            queryset = queryset.filter(tag__in=OPERATOR_TAGS)
        elif tag:
            queryset = queryset.filter(tag=tag)
        if ai_qualified:
            queryset = queryset.filter(customer__in=list(Customer.objects(ai_qualified_at__ne=None).scalar('id')))
        if needs_attention is not None:
            queryset = queryset.filter(needs_attention=needs_attention)
        if assignee == 'none':
            queryset = queryset.filter(assignee=None)
        elif assignee:
            queryset = queryset.filter(assignee=assignee)
        return queryset

    @staticmethod
    def get_closed_conversations_in_period(start_dt, end_dt):
        try:
            return ConversationModel.objects(
                created_at__gte=start_dt,
                created_at__lte=end_dt,
                status="CLOSED"
            )
        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao buscar conversas fechadas no período: {e}")
            raise e
    @staticmethod
    def search_contacts(search_term: str, status: str, limit: int = 10):
        """Busca contatos e associa a conversa mais recente da aba solicitada."""
        try:
            customer_filter = Q(name__icontains=search_term) | Q(phone__icontains=search_term)
            phone_term = re.sub(r'\D', '', search_term)
            if phone_term and phone_term != search_term:
                customer_filter |= Q(phone__icontains=phone_term)

            customers = Customer.objects(customer_filter).order_by('-updated_at')

            results = []
            for customer in customers:
                conversation = ConversationModel.objects(
                    customer=customer,
                    status=status,
                ).order_by('-updated_at').first()

                # Na aba de fechadas, contatos sem conversa fechada não são úteis.
                if status == 'CLOSED' and conversation is None:
                    continue

                results.append({
                    'customer': customer,
                    'conversation': conversation,
                })
                if len(results) >= limit:
                    break

            return results
        except Exception as e:
            logger.error(f"[ConversationRepository] Erro ao buscar contatos do chat: {e}")
            raise e
