from crm.models.custumer_model import Customer
from crm.interfaces.customer_repository_interface import ICustomerRepository
from database.client.mongodb_client import MongoDBClient
from bson import ObjectId
from mongoengine.queryset.visitor import Q


class CustomerRepository(ICustomerRepository):
    def __init__(self, database_client: MongoDBClient):
        self.db = database_client

    def get_customers(self, ids: list[str]) -> list[dict]:
        with self.db.get_connection_context():
            if not ids:
                return []

            # Converte strings para ObjectId
            object_ids = []
            for id_str in ids:
                try:
                    object_ids.append(ObjectId(id_str))
                except:
                    continue

            customers = Customer.objects(id__in=object_ids)
            return [customer.to_dict() for customer in customers]

    def get_all_customers(self, status_filter: str | None = None, search_term: str | None = None) -> list[dict]:
        with self.db.get_connection_context():
            customers = Customer.objects()

            if status_filter and status_filter != 'all':
                customers = customers.filter(customer_state_now=status_filter)

            if search_term:
                customers = customers.filter(
                    Q(name__icontains=search_term) |
                    Q(phone__icontains=search_term) |
                    Q(event_title__icontains=search_term) |
                    Q(celebration_type__icontains=search_term)
                )

            customers = customers.order_by('-updated_at')
            return [customer.to_dict() for customer in customers]

    def find(self, id: str | None = None, phone: str | None = None) -> dict | None:
        with self.db.get_connection_context():
            query_params = {}

            if id:
                try:
                    query_params["id"] = ObjectId(id)
                except:
                    return None

            if phone:
                query_params["phone"] = phone

            customer = Customer.objects(**query_params).first()

            return customer.to_dict() if customer else None


    def find_user_by_mongo_logic(self, **kwargs) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(**kwargs).first()

            return customer.to_dict() if customer else None

    def get_customer_by_filters(self, **kwargs) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(**kwargs)

            return [customer.to_dict() for customer in customer]

    def create(
        self,
        name: str,
        phone: str | list,
        agent: str | None = None,
    ) -> dict:
        with self.db.get_connection_context():
            customer = Customer(
                name=name,
                phone=phone,
                agent=agent
            )
            customer.save()
            return customer.to_dict()

    def update_name(
        self,
        name: str,
        phone: str,
    ) -> bool:
        with self.db.get_connection_context():
            customer = Customer.objects(phone=phone).first()
            if not customer:
                return False

            customer.name = name
            customer.save()
            return True

    def update(
        self,
        id: str,
        attributes: dict = {},
    ) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(id=ObjectId(id)).first()
            if not customer:
                return None

            for key, value in attributes.items():
                if key in [
                    "name",
                    "phone",
                    "agent",
                    "customer_state_now",
                    "blocked_until",
                    "new_service"
                ]:
                    setattr(customer, key, value)

            customer.updated_at = attributes.get("updated_at", customer.updated_at)
            customer.save()
            return customer.to_dict()

    def exists(self, phone: str) -> bool:
        with self.db.get_connection_context():
            return Customer.objects(phone=phone).count() > 0

    def get_customers_needing_follow_up(self) -> list[dict]:
        """
        Retorna todos os customers que precisam de follow-up.

        Critérios:
        - needs_follow_up = True
        - follow_up_done = False

        A lógica de negócio para determinar se uma conversa foi realmente abandonada
        é feita em um serviço específico.
        """
        with self.db.get_connection_context():
            customers = Customer.objects(needs_follow_up=True, follow_up_done=False)
            return [customer.to_dict() for customer in customers]

    def get_by_id(self, id: str) -> dict | None:
        with self.db.get_connection_context():
            try:
                customer = Customer.objects(id=ObjectId(id)).first()
                return customer.to_dict() if customer else None
            except:
                return None

    def get_by_phone(self, phone: str) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(phone=phone).first()
            return customer.to_dict() if customer else None

    def delete_customer(self, customer_id: str) -> bool:
        with self.db.get_connection_context():
            customer = Customer.objects(id=ObjectId(customer_id)).first()
            if not customer:
                return False

            customer.delete()
            return True
