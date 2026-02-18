from container.clients import ClientContainer
from repositories.message_repository import MessageRepository
from repositories.customer_repository import CustomerRepository


class RepositoryContainer:

    def __init__(self, clients: ClientContainer):
        self._clients = clients

    @property
    def message(self) -> MessageRepository:
        return MessageRepository(database_client=self._clients.database)

    @property
    def customer(self) -> CustomerRepository:
        return CustomerRepository(database_client=self._clients.database)
