from abc import ABC, abstractmethod


class IManagerRepository(ABC):
    @abstractmethod
    def get_managers(self, ids: list[str]) -> list[dict]:
        """Retrieve all managers."""
        pass

    @abstractmethod
    def find(self, email: str )-> dict | None:
        """find a manager by email."""
        pass

    @abstractmethod
    def find_by_mongo_logic(self, **kwargs) -> dict | None:
        """Retrieve all managers."""
        pass

    @abstractmethod
    def create(
        self,
        name: str,
        email: str,
        password_hash: str,
    ) -> dict:
        """Create a new manager."""
        pass

    @abstractmethod
    def update(self, email: str, attributes: dict = {}):
        """Update an existing manager."""
        pass
