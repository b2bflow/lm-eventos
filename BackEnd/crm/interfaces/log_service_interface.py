from abc import ABC, abstractmethod
from typing import List, Any

class ILogService(ABC):
    @abstractmethod
    def create_log(self, customer_id: str, operator_id: str, action_type: str, description: str) -> Any:
        pass

    @abstractmethod
    def get_customer_logs(self, customer_id: str) -> List[Any]:
        pass