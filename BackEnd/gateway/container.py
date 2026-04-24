import os
from utils.logger import logger
from gateway.adapters.zapi_adapter import ZAPIClient
from gateway.interfaces.chat_interface import IChat


class GatewayContainer:
    
    @property
    def chat(self) -> ZAPIClient:
        return ZAPIClient()