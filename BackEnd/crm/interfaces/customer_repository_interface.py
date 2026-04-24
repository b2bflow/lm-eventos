from abc import ABC, abstractmethod


class ICustomerRepository(ABC):
    def get_customers(self, ids: list[str]) -> list[dict]:
        pass

    def get_all_customers(self) -> list[dict]:
        """Retrieve all customers."""
        pass

    @abstractmethod
    def find(self, id: str | None = None, phone: str | None = None) -> dict | None:
        """Retrieve all messages."""
        pass

    @abstractmethod
    def find_user_by_mongo_logic(self, **kwargs) -> dict | None:
        """Retrieve all messages."""
        pass

    @abstractmethod
    def get_customer_by_filters(self, **kwargs) -> dict | None:
        """Retrieve all customers that match the given filters."""
        pass

    @abstractmethod
    def create(
        self,
        name: str,
        phone: str | list,
        agent: str | None = None,
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
        attributes: dict = {},
    ) -> dict | None:
        """Update an existing customer."""
        pass

    @abstractmethod
    def exists(self, phone: str) -> bool:
        """Check if a customer exists by phone number."""
        pass

    @abstractmethod
    def get_customers_needing_follow_up(self) -> list[dict]:
        """
        Retrieve all customers that need follow-up.

        Returns customers with needs_follow_up=True and follow_up_done=False.
        The business logic to determine if a conversation is actually abandoned
        is handled by the AbandonedConversationService.
        """
        pass
