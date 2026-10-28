"""Chats internos da aba WhatsApp (como o Arquivadas do WhatsApp): conversas da equipe que não têm
a ver com a IA nem com orçamento e que são vistas pelo celular.

A marca fica no contato (Customer.internal_chat), então as próximas conversas dele também ficam
nos Chats internos. Mover para lá pausa a IA; tirar de lá não religa a IA sozinho.
"""
from chat.models.conversation_model import ConversationModel
from chat.services.handover_service import ConversationHandoverService, _get, user_display_name


class InternalChatService:
    def __init__(self, handover: ConversationHandoverService | None = None):
        self.handover = handover or ConversationHandoverService()

    def set_internal(self, conversation_id: str, internal: bool, user=None) -> ConversationModel:
        conversation = _get(conversation_id)
        customer = conversation.customer
        if not customer:
            raise ValueError("Conversa sem contato.")
        internal = bool(internal)
        if bool(customer.internal_chat) == internal:
            return conversation

        customer.update(set__internal_chat=internal)
        customer.reload()
        name = user_display_name(user)
        if internal and (conversation.tag == 'AGENTE' or conversation.ai_active):
            text = f"Conversa movida para os Chats internos por {name}. IA pausada nesta conversa."
            return self.handover._switch(conversation, 'OPERADOR', text, user)

        text = (f"Conversa movida para os Chats internos por {name}." if internal
                else f"Conversa tirada dos Chats internos por {name}.")
        self.handover._internal(conversation, text, 'event', user)
        return conversation
