from utils.logger import logger, to_json_dump
from interfaces.clients.chat_interface import IChat
from os import getenv
from utils.logger import logger


class AutomationIsPausedService:
    def __init__(self, chat_client: IChat):
        self.chat = chat_client
        self.tag_ids: list[str] = [
            getenv("ZAPI_PAUSED_AUTOMATION_TAG_ID"),
            getenv("ZAPI_ORDER_TAG_ID"),
            getenv("ZAPI_REGISTER_TAG_ID"),
            getenv("ZAPI_UNREGISTER_TAG_ID"),
            getenv("ZAPI_URGENT_TAG_ID"),
            getenv("ZAPI_SUPPLIER_TAG_ID"),
            getenv("ZAPI_RENEGOTIATION_TAG_ID"),
        ]

    def check(self, phone: str) -> bool:
        chat_metadata: dict = self.chat.get_chat_metadata(phone=phone)

        logger.info(f"[AUTOMATION_IS_PAUSED_SERVICE] Checando chat metadata: {chat_metadata.get('tags')}")

        if not chat_metadata:
            return False

        if chat_metadata.get("tags", []) and any(
            tag in chat_metadata.get("tags", []) for tag in self.tag_ids
        ):
            logger.info(
                f"[AUTOMATION IS PAUSED SERVICE] Automação pausada para o número {phone}. Mensagem não adicionada a fila."
            )

            return True

        return False
