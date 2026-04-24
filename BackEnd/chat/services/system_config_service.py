from utils.logger import logger
from chat.repositories.system_config_repository import SystemConfigRepository
from chat.models.system_config_model import SystemConfig


class SystemConfigService:
    
    @staticmethod
    def get_configuration() -> SystemConfig:
        try:
            return SystemConfigRepository.get_config()
        except Exception as e:
            logger.error(f"[SystemConfigService] Falha ao recuperar configuração: {e}")
            raise RuntimeError("Erro interno ao ler configurações do sistema.")

    @staticmethod
    def update_configuration(data: dict) -> SystemConfig:
        try:
            logger.info("[SystemConfigService] Administrador a atualizar as configurações globais do sistema.")
            return SystemConfigRepository.update_config(data)
        except Exception as e:
            logger.error(f"[SystemConfigService] Falha ao atualizar configuração: {e}")
            raise RuntimeError("Erro interno ao guardar configurações do sistema.")