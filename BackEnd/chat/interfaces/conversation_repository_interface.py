from chat.models.conversation_model import ConversationModel
from crm.models.custumer_model import Customer


class IConversationRepository:
    @staticmethod
    def get_by_id(conversation_id: str) -> ConversationModel | None:
        ...

    @staticmethod
    def get_active_conversation(customer: Customer) -> ConversationModel | None:
        ...

    @staticmethod
    def create_conversation(customer) -> ConversationModel: # Removi a tipagem rígida de Customer aqui para evitar avisos da IDE
        ...

    @staticmethod
    def update_conversation(conversation: ConversationModel):
        ...

    @staticmethod
    def get_all_ordered_by_interaction():
        ...

    @staticmethod
    def get_closed_conversations_in_period(start_dt, end_dt):
        ...