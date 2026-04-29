from chat.models.conversation_model import ConversationModel
from chat.repositories.system_config_repository import SystemConfigRepository
from crm.models.custumer_model import Customer
from mongoengine.errors import DoesNotExist
from chat.interfaces.conversation_repository_interface import IConversationRepository
from utils.logger import logger
from datetime import datetime


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
                tag='AGENTE'
            )
            conv.save()

            # Ajuste aqui: Se 'customer' for string, usa ela direto. Se for objeto, pega o .id
            customer_id = customer if isinstance(customer, str) else str(getattr(customer, 'id', customer))

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
