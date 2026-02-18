import json
from database.models.customer_model import Customer
from interfaces.repositories.customer_repository_interface import ICustomerRepository
from interfaces.clients.database_interface import IDatabase
from bson import ObjectId


class CustomerRepository(ICustomerRepository):
    def __init__(self, database_client: IDatabase):
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

    def create(
        self,
        name: str,
        phone: str | list,
    ) -> dict:
        with self.db.get_connection_context():
            customer = Customer(
                name=name,
                phone=phone,
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
        attributes: dict,
    ) -> dict | None:
        with self.db.get_connection_context():
            customer = Customer.objects(id=ObjectId(id)).first()
            if not customer:
                return None

            for key, value in attributes.items():
                if key in ["name", "phone", "tag", "contract_data", "agent"]:
                    setattr(customer, key, value)

            customer.save()
            return customer.to_dict()

    def exists(self, phone: str) -> bool:
        with self.db.get_connection_context():
            return Customer.objects(phone=phone).count() > 0
