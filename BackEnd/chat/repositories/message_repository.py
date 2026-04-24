from mongoengine.errors import NotUniqueError, DoesNotExist
from chat.interfaces.message_repository_interface import IMessageRepository
from chat.models.message_model import MessageModel
from chat.models.conversation_model import ConversationModel
from utils.logger import logger


class MessageRepository(IMessageRepository):
    @staticmethod
    def get_by_id(message_id: str) -> MessageModel | None:
        try:
            return MessageModel.objects.get(id=message_id)
        except DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagem por ID: {e}")
            raise e

    @staticmethod
    def create(
        conversation: ConversationModel,
        direction: str,
        content: str,
        role: str = None,
        status: str = 'QUEUED', 
        external_id: str = None,
        raw_metadata: dict = None
    ) -> MessageModel:
        
        if not role:
            role = 'user' if direction == 'INCOMING' else 'assistant'

        msg = MessageModel(
            conversation=conversation,
            customer=conversation.customer,  
            role=role,
            direction=direction,
            status=status, 
            content=content,
            external_id=external_id,
            raw_metadata=raw_metadata or {}
        )
        
        try:
            msg.save()
            return msg
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao criar mensagem: {e}")
            raise e

    @staticmethod
    def get_recent_context(conversation_id: str, limit: int = 100) -> list:
        try:
            messages = MessageModel.objects(conversation=conversation_id).order_by('-created_at')[:limit]
            return list(messages)[::-1]
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar contexto recente da conversa {conversation_id}: {e}")
            raise e

    @staticmethod
    def update_message_status(message: MessageModel, status: str = None, external_id: str = None, error_message: str = None) -> MessageModel:
        try:
            if status:
                message.status = status
            if external_id:
                message.external_id = external_id
            if error_message:
                message.error_message = error_message
            message.save()
            return message
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao atualizar status da mensagem {message.id}: {e}")
            raise e

    @staticmethod
    def get_messages_by_conversation(conversation_id: str):
        try:
            return MessageModel.objects(conversation=conversation_id).order_by('created_at')
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagens da conversa {conversation_id}: {e}")
            raise e

    @staticmethod
    def get_messages_by_customer(customer_id: str):
        try:
            return MessageModel.objects(customer=customer_id).order_by('created_at')
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagens do paciente {customer_id}: {e}")
            raise e
            
    @staticmethod
    def get_empty_queryset():
        return MessageModel.objects.none()
    
    @staticmethod
    def mark_as_read_by_conversation(conversation_id: str):
        try:
            MessageModel.objects(
                conversation=conversation_id, 
                direction='INCOMING', 
                status__ne='READ'
            ).update(set__status='READ')
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao marcar mensagens como lidas na conversa {conversation_id}: {e}")
            raise e
        
    def get_latest_customer_messages(self, customer_id: str | None = None, limit: int = 20) -> list:
        if not customer_id:
            return []

        try:
            # 1. Filtra diretamente no MessageModel usando o campo 'customer'
            # 2. Ordena de forma decrescente para que o limit corte as mensagens mais recentes
            messages_query = MessageModel.objects(customer=customer_id).order_by("-created_at")

            if limit:
                messages_query = messages_query.limit(limit)

            # 3. Converte os objetos do MongoDB para dicionário (esperado pelo _prepare_context)
            messages_list = [msg.to_dict() for msg in messages_query]

            # 4. Inverte a lista para ficar em ordem cronológica (antigas -> recentes)
            # Sem isso, a IA recebe o contexto de trás pra frente e fica confusa.
            messages_list.reverse()
            
            return messages_list

        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar últimas mensagens: {e}")
            return []
        
    def dele_all_customer_messages(self, customer_id: str) -> None:
        try:
            MessageModel.objects(customer=customer_id).delete()
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao deletar mensagens do cliente {customer_id}: {e}")
            raise e
    
    def get_customer_messages(self, customer_id: str) -> list:
        try:
            messages = MessageModel.objects(customer=customer_id).order_by('created_at')
            return list(messages)
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagens do cliente {customer_id}: {e}")
            raise e
        
    def all(self) -> list:
        try:
            return list(MessageModel.objects().order_by('created_at'))
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar todas as mensagens: {e}")
            raise e
        
    def all_by_customer(self, customer_id: str) -> list:
        try:
            return list(MessageModel.objects(customer=customer_id).order_by('created_at'))
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagens do cliente {customer_id}: {e}")
            raise e
        
    def get_last_customer_message(self, customer_id: str) -> dict | None:
        try:
            message = MessageModel.objects(customer=customer_id).order_by('-created_at').first()
            return message.to_dict() if message else None
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar última mensagem do cliente {customer_id}: {e}")
            raise e 
        
    def get_customer_messages(self, customer_id: str) -> list:
        try:
            messages = MessageModel.objects(customer=customer_id).order_by('created_at')
            return list(messages)
        except Exception as e:
            logger.error(f"[MessageRepository] Erro ao buscar mensagens do cliente {customer_id}: {e}")
            raise e
        
        