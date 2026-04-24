from utils.logger import logger
from chat.models.system_config_model import SystemConfig


class SystemConfigRepository:
    @staticmethod
    def get_config() -> SystemConfig:
        config = SystemConfig.objects.first()
        if not config:
            config = SystemConfig().save()
            logger.info(f"[SystemConfig] Documento mestre criado: {config.id}")
        return config

    @staticmethod
    def update_config(data: dict) -> SystemConfig:
        config = SystemConfigRepository.get_config()
        
        logger.info(f"[SystemConfig] Tentando salvar dados: {data}")

        for key, value in data.items():
            if hasattr(config, key) and key != 'id':
                setattr(config, key, value)
        
        config.save()
        config.reload() 
        logger.info(f"[SystemConfig] Dados persistidos com sucesso no ID: {config.id}")
        return config