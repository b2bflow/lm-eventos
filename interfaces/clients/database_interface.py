from abc import ABC, abstractmethod
from typing import Generator, Any


class IDatabase(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Conecta ao banco de dados"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Desconecta do banco de dados"""
        pass

    @abstractmethod
    def get_connection_context(self) -> Generator[Any, None, None]:
        """Retorna um context manager para transações"""
        pass
