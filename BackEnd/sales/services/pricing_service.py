from crm.models.lm_settings_model import LmSettings
from sales.catalog import merge_price_table
from sales.services.quote_calculator import CalcConfig


def effective_price_table() -> dict:
    """Catálogo padrão + edições da Erica em LmSettings.price_table."""
    return merge_price_table(LmSettings.get().price_table)


def calc_config() -> CalcConfig:
    return CalcConfig.from_settings(LmSettings.get())
