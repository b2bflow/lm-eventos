from abc import ABC, abstractmethod
from typing import List, Any

class ICustomerService(ABC):
    @abstractmethod
    def register_customer(self, data: dict, user: Any = None) -> Any:
        pass

    @abstractmethod
    def get_active_customers(self) -> List[Any]:
        pass

    @abstractmethod
    def update_customer_info(self, customer_id: str, data: dict, user: Any = None) -> Any:
        pass

    @abstractmethod
    def delete_customer(self, customer_id: str, user: Any = None) -> bool:
        pass

    @staticmethod
    @abstractmethod
    def get_customer_name_by_id(customer_id: str) -> str:
        pass

    @staticmethod
    @abstractmethod
    def get_customer_by_phone(phone: str) -> Any:
        pass