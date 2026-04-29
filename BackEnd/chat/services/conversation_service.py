from typing import Optional
from utils.logger import logger
from chat.repositories.conversation_repository import ConversationRepository
from chat.repositories.message_repository import MessageRepository
from chat.interfaces.chat_service_interface import IConversationService
from crm.services.quote_service import QuoteService


class ConversationService(IConversationService):
    def __init__(self):
        self.conversation_repo = ConversationRepository()
        self.message_repo = MessageRepository()
        self.quote_service = QuoteService()

    def get_all_conversations(self):
        try:
            return self.conversation_repo.get_all_ordered_by_interaction()
        except Exception as e:
            logger.error(f"[ConversationService] Erro ao listar conversas: {e}")
            raise e

    def update_conversation(self, conversation_id: str, data: dict, user=None):
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation: 
                raise ValueError("Conversa não encontrada.")            
            
            if 'tag' in data:
                conversation.tag = data['tag']
                conversation.ai_active = (data['tag'] == 'AGENTE')
                if data['tag'] in ['OPERADOR', 'operador_humano', 'orcamento']:
                    conversation.needs_attention = True
                
            if 'status' in data and data['status'] in ['OPEN', 'CLOSED', 'ARCHIVED']:
                conversation.status = data['status']
                if data['status'] == 'CLOSED':
                    final_status = data.get('final_customer_status') or getattr(conversation.customer, 'customer_state_now', 'ANALYSIS')
                    conversation.final_customer_status = final_status
                    if not getattr(conversation, 'quote', None) and final_status in ['WON', 'LOST']:
                        from crm.models.quote_model import Quote
                        quote = self.quote_service.get_or_create_active_quote_for_customer(str(conversation.customer.id))
                        conversation.quote = Quote.objects(id=quote.get("id")).first()

                    if getattr(conversation, 'quote', None) and final_status in ['WON', 'LOST']:
                        close_payload = {
                            key: value
                            for key, value in {
                                "contract_value": data.get("contract_value"),
                                "notes": data.get("notes"),
                            }.items()
                            if value not in (None, "")
                        }
                        self.quote_service.close_quote(
                            quote_id=str(conversation.quote.id),
                            status_value=final_status,
                            data=close_payload,
                            user=user,
                        )

            if 'needs_attention' in data:
                conversation.needs_attention = data['needs_attention']

            return self.conversation_repo.update_conversation(conversation)
        except Exception as e:
            logger.error(f"[ConversationService] Erro ao atualizar conversa: {e}")
            raise e
        
    def mark_conversation_as_read(self, conversation_id: str):
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                raise ValueError("Conversa não encontrada.")
            
            self.message_repo.mark_as_read_by_conversation(conversation_id)
            
            conversation.needs_attention = False
            conversation.unread_count = 0
            return self.conversation_repo.update_conversation(conversation)
        except Exception as e:
            logger.error(f"[ConversationService] Erro ao marcar como lido: {e}")
            raise e

    def get_ai_context(self, conversation_id: str) -> Optional[dict]:
        try:
            conversation = self.conversation_repo.get_by_id(conversation_id)
            if not conversation:
                logger.warning(f"[ConversationService] Conversa {conversation_id} não encontrada.")
                return None

            phone = getattr(conversation.customer, 'phone', None)
            customer_name = getattr(conversation.customer, 'name', None)

            if not phone:
                logger.warning(f"[ConversationService] Lead sem telefone na conversa {conversation_id}.")
                return None

            raw_messages = self.message_repo.get_recent_context(conversation_id, limit=100)
            history = []
            for msg in raw_messages:
                if not msg.content:
                    continue
                content = msg.content.strip()
                if not content:
                    continue
                role = msg.role
                if role in ["OPERATOR", "BOT"]:
                    role = "assistant"
                elif role == "SYSTEM":
                    role = "developer"
                elif role not in ["user", "assistant"]:
                    role = "user"
                history.append({
                    "role": role,
                    "content": content
            })

            return {
                "phone": phone,
                "customer_name": customer_name,
                "history": history
            }
        except Exception as e:
            logger.error(f"[ConversationService] Erro ao gerar contexto de IA: {e}")
            return None

    def get_closed_conversations_in_period(self, start_dt, end_dt):
        try:
            return self.conversation_repo.get_closed_conversations_in_period(start_dt, end_dt)
        except Exception as e:
            logger.error(f"[ConversationService] Erro ao buscar conversas do período: {e}")
            raise e
