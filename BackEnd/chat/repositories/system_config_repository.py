from utils.logger import logger
from chat.models.system_config_model import SystemConfig


class SystemConfigRepository:
    EDITABLE_FIELDS = {"webhook_token", "zapi_instance_id", "zapi_token", "openai_api_key", "ai_active"}
    SECRET_FIELDS = {"webhook_token", "zapi_token", "openai_api_key"}

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
        
        logger.info(f"[SystemConfig] Atualizando campos: {sorted(data.keys())}")

        for key, value in data.items():
            if key not in SystemConfigRepository.EDITABLE_FIELDS:
                continue
            # Segredo devolvido mascarado pelo GET: não sobrescreve o valor real.
            if key in SystemConfigRepository.SECRET_FIELDS and (not value or str(value).startswith("••••")):
                continue
            setattr(config, key, value)
        
        config.save()
        config.reload() 
        logger.info(f"[SystemConfig] Dados persistidos com sucesso no ID: {config.id}")
        return config