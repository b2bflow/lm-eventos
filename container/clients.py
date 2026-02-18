from clients.zapi_client import ZAPIClient
from clients.openai_client import OpenIAClient
from clients.mongodb_client import MongoDBClient
from clients.redis_client import RedisClient
from clients.google_sheets_client import GoogleSheetsClient


class ClientContainer:
    def __init__(self):
        self._chat_instance: ZAPIClient | None = None

    @property
    def chat(self) -> ZAPIClient:
        if self._chat_instance is None:
            self._chat_instance = ZAPIClient()
        return self._chat_instance

    @property
    def ai(self) -> OpenIAClient:
        return OpenIAClient()

    @property
    def database(self) -> MongoDBClient:
        return MongoDBClient()

    @property
    def cache(self) -> RedisClient:
        return RedisClient()

    @property
    def spreadsheet(self) -> GoogleSheetsClient:
        return GoogleSheetsClient()
