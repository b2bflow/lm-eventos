from abc import ABC, abstractmethod


class IAI(ABC):

    @abstractmethod
    def function_call_output(
        self,
        function_call_id: str,
        call_id: str,
        call_name: str,
        output: str,
        arguments: dict,
        model: str,
    ) -> tuple[list, dict]:
        pass

    @abstractmethod
    def transcribe_audio(self, audio_bytes: str) -> str:
        pass

    @abstractmethod
    def create_model_response(
        self,
        model: str,
        input: str | list,
        tools: list = None,
        instructions: str | None = None,
        reasoning: str = "none",
        verobosity: str = "low",
        include: list = [],
    ) -> dict:
        pass
