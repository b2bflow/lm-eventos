from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class IDashboardService(ABC):
    @abstractmethod
    def get_general_metrics(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        pass