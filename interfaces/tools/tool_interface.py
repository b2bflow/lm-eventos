from abc import ABC, abstractmethod


class ITool(ABC):
    @property
    def name(self) -> str | None:
        return None

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def execute(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        customer: dict,
        context: list,
        arguments: dict,
    ) -> list[dict]: ...
