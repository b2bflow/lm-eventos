from gateway.adapters.zapi_adapter import ZAPIClient
from ai_agents.clients.openai_client import OpenIAClient
from database.client.mongodb_client import MongoDBClient


class ClientContainer:
    @classmethod
    def chat(self) -> ZAPIClient:
        return ZAPIClient()

    @classmethod
    def ai(self) -> OpenIAClient:
        return OpenIAClient()

    @classmethod
    def database(self) -> MongoDBClient:
        return MongoDBClient()
