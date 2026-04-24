
from ai_agents.containers.client_container import  ClientContainer
from chat.repositories.message_repository import MessageRepository
from crm.repositories.customer_repository import CustomerRepository
from chat.repositories.conversation_repository import ConversationRepository

class RepositoryContainer:

    def __init__(self, clients: ClientContainer):
        self._clients = clients

    @property
    def message(self) -> MessageRepository:
        return MessageRepository()

    @property
    def customer(self) -> CustomerRepository:
        return CustomerRepository(database_client=self._clients.database())


    @property
    def conversation(self):
        return ConversationRepository()


