import json
from interfaces.repositories.message_repository_interface import IMessageRepository
from database.models.message_model import Message
from database.models.customer_model import Customer
from interfaces.clients.database_interface import IDatabase
from bson import ObjectId


class MessageRepository(IMessageRepository):
    def __init__(self, database_client: IDatabase):
        self.db = database_client

    def all(self) -> list:
        with self.db.get_connection_context():
            messages = Message.objects()
            return [message.to_dict() for message in messages] or []

    def get_latest_customer_messages(
        self, customer_id: str | None = None, limit: int = 20
    ) -> list:
        with self.db.get_connection_context():
            if not customer_id:
                return []

            try:
                # Busca o customer pelo ID (string)
                customer = Customer.objects(id=ObjectId(customer_id)).first()
                if not customer:
                    return []

                # Busca mensagens referenciando esse customer
                messages = Message.objects(customer_id=customer).order_by("-id")

                if limit:
                    messages = messages.limit(limit)

                return [message.to_dict() for message in messages] or []
            except:
                return []

    def create(
        self,
        customer_id: str,
        role: str,
        content: str | list,
    ) -> dict:
        with self.db.get_connection_context():
            # Busca o customer pelo ID
            customer = Customer.objects(id=ObjectId(customer_id)).first()
            if not customer:
                raise ValueError(f"Customer com ID {customer_id} não encontrado")

            message = Message(
                customer_id=customer,
                role=role,
                content=content if isinstance(content, str) else json.dumps(content),
            )
            message.save()
            return message.to_dict()
