from abc import ABC, abstractmethod


class IChat(ABC):

    @abstractmethod
    def after_send(
        self, event: str, hook: callable, args: tuple = (), kwargs: dict = {}
    ) -> None:
        pass

    @abstractmethod
    def clear_after_send_hooks(self, hooks: list[dict]) -> None:
        pass

    @abstractmethod
    def set_instance(self, instance: str, instance_key: str) -> None:
        pass

    @abstractmethod
    def send_message(self, phone: str, message: str) -> bool:
        pass

    @abstractmethod
    def send_contact(self, phone: str, name: str, contact_phone: str) -> dict:
        pass

    @abstractmethod
    def send_document(
        self,
        phone: str,
        document: str,
        extension: str,
        file_name: str = "",
        caption: str = "",
    ) -> bool:
        pass

    @abstractmethod
    def send_image(self, phone: str, image: str, caption: str | None = None) -> bool:
        pass

    @abstractmethod
    def get_message(self, **kwargs) -> str:
        pass

    @abstractmethod
    def get_phone(self, **kwargs) -> str:
        pass

    @abstractmethod
    def is_valid_message(self, **kwargs) -> bool:
        pass

    @abstractmethod
    def is_audio_message(self, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_audio_bytes(self, **kwargs) -> str:
        pass

    @abstractmethod
    def is_image(self, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_image_url(self, **kwargs) -> str:
        pass

    @abstractmethod
    def get_image_caption(self, **kwargs) -> str:
        pass

    @abstractmethod
    def is_file(self, **kwargs) -> bool:
        pass

    @abstractmethod
    def get_file_url(self, **kwargs) -> str:
        pass

    @abstractmethod
    def get_file_caption(self, **kwargs) -> str:
        pass

    @abstractmethod
    def get_name(self, **kwargs) -> str:
        pass

    @abstractmethod
    def assign_tag_to_chat(self, phone: str, tag_id: int) -> bool:
        pass

    @abstractmethod
    def remove_tag_from_chat(self, phone: str, tag_id: int) -> bool:
        pass

    @abstractmethod
    def get_chat_metadata(self, phone: str) -> dict:
        pass
