from typing import Generator, Any
from contextlib import contextmanager
from database.config import connect_database, disconnect_database
from database.inteface.dabase_interface import IDatabase
from mongoengine.connection import get_connection, ConnectionFailure

class MongoDBClient(IDatabase):
    def __init__(self):
        self._connection = None

    def connect(self) -> None:
        """Conecta ao MongoDB usando MongoEngine, reaproveitando a conexão se já existir"""
        if not self._connection:
            try:
                # Tenta recuperar a conexão global 'default' já existente
                self._connection = get_connection()
            except ConnectionFailure:
                # Se não existir nenhuma conexão global aberta, então cria uma nova
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
            raise e
        finally:
            pass