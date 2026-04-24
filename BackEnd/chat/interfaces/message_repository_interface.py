from abc import ABC, abstractmethod


class IMessageRepository(ABC):
    @abstractmethod
    def all(self) -> list:
        """Retrieve all messages."""
        pass

    @abstractmethod
    def all_by_customer(self, customer_id: str) -> list:
        """Retrieve all messages for a given customer ID."""
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

    def get_last_customer_message(self, customer_id: str) -> dict | None:
        """Retrieve the last message for a given customer ID."""
        pass

    @abstractmethod
    def dele_all_customer_messages(self, customer_id: str) -> None:
        """Delete all messages for a given customer ID."""
        ...
    @abstractmethod
    def get_customer_messages(self, customer_id: str) -> list:
        """Get all messages for a given customer ID."""
        ...
