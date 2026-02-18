from typing import Generator, Any
from contextlib import contextmanager
from database.config import connect_database, disconnect_database
from interfaces.clients.database_interface import IDatabase


class MongoDBClient(IDatabase):
    def __init__(self):
        self._connection = None

    def connect(self) -> None:
        """Conecta ao MongoDB usando MongoEngine"""
        if not self._connection:
            self._connection = connect_database()

    def disconnect(self) -> None:
        """Desconecta do MongoDB"""
        if self._connection:
            disconnect_database()
            self._connection = None

    @contextmanager
    def get_connection_context(self) -> Generator[Any, None, None]:
        """Context manager para operações no MongoDB"""
        try:
            if not self._connection:
                self.connect()
            yield self._connection
        except Exception as e:
            # Em caso de erro, pode implementar rollback se necessário
            raise e
        finally:
            # MongoDB não precisa de commit explícito como PostgreSQL
            pass
