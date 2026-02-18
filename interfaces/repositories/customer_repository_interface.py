from abc import ABC, abstractmethod


class ICustomerRepository(ABC):
    def get_customers(self, ids: list[str]) -> list[dict]:
        pass

    @abstractmethod
    def find(self, id: str | None = None, phone: str | None = None) -> dict | None:
        """Retrieve all messages."""
        pass

    @abstractmethod
    def create(
        self,
        name: str,
        phone: str | list,
    ) -> dict:
        """Create a new customer."""
        pass

    @abstractmethod
    def update_name(
        self,
        name: str,
        phone: str,
    ) -> bool:
        """Update an existing customer."""
        pass

    @abstractmethod
    def update(
        self,
        id: str,
        attributes: dict,
    ) -> dict | None:
        """Update an existing customer."""
        pass

    @abstractmethod
    def exists(self, phone: str) -> bool:
        """Check if a customer exists by phone number."""
        pass
