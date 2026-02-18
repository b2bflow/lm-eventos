from abc import ABC, abstractmethod


class IMessageRepository(ABC):
    @abstractmethod
    def all(self) -> list:
        """Retrieve all messages."""
        pass

    @abstractmethod
    def get_latest_customer_messages(
        self, customer_id: str | None = None, limit: int = 20
    ) -> list:
        """Retrieve the latest message for a given customer ID."""
        pass

    @abstractmethod
    def create(
        self,
        customer_id: str,
        role: str,
        content: str | list,
    ) -> dict:
        """Create a new message."""
        pass
