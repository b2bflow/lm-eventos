from database.models.mananger_model import Manager
from interfaces.clients.database_interface import IDatabase
from bson import ObjectId

from interfaces.repositories.manager_repository_interface import IManagerRepository


class ManagerRepository(IManagerRepository):
    def __init__(self, database_client: IDatabase):
        self.db = database_client

    def get_managers(self, ids: list[str]) -> list[dict]:
        with self.db.get_connection_context():
            if not ids:
                return []

            object_ids = []
            for id_str in ids:
                try:
                    object_ids.append(ObjectId(id_str))
                except:
                    continue

            managers = Manager.objects(id__in=object_ids)
            return [manager.to_dict() for manager in managers]

    def find(self, email: str) -> dict | None:
        with self.db.get_connection_context():
            query_params = {}

            if email:
                query_params["email"] = email

            manager = Manager.objects(**query_params).first()

            return manager.to_dict() if manager else None

    def find_by_mongo_logic(self, **kwargs) -> dict | None:
        with self.db.get_connection_context():
            manager = Manager.objects(**kwargs).first()

            return manager.to_dict() if manager else None


    def create(
        self,
        name: str,
        email: str,
        password_hash: str
    ) -> dict:
        with self.db.get_connection_context():
            manager = Manager(
                name=name,
                password_hash=password_hash,
                email=email,
            )
            manager.save()
            return manager.to_dict()

    def update(self, email: str, attributes: dict = {}):
        with self.db.get_connection_context():
            manager = Manager.objects(email=email).first()
            manager.update(**attributes)
            manager.save()
            return manager.to_dict()