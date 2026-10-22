from crm.models.lm_settings_model import LmSettings
from sales.catalog import CATALOG_BY_CODE, catalog_item_from_inventory, merge_price_table
from sales.services.quote_calculator import CalcConfig


def effective_price_table() -> dict:
    """Catálogo padrão + edições da Erica em LmSettings.price_table. `extra_items` traz os itens
    alugáveis criados pela tela de Estoque (fora do CATALOG), para a calculadora conhecê-los."""
    from inventory.models import InventoryItem

    table = merge_price_table(LmSettings.get().price_table)
    table["extra_items"] = {
        doc.code: catalog_item_from_inventory(doc)
        for doc in InventoryItem.objects(active=True, rentable=True, code__nin=list(CATALOG_BY_CODE))
    }
    return table


def set_item_price(code: str, price) -> None:
    """Grava (ou limpa, com None) o preço de venda de um item em LmSettings.price_table.

    Torres cobradas por metro: o preço gravado vale por peça e substitui o cálculo pelo metro."""
    settings = LmSettings.get()
    table = dict(settings.price_table or {})
    items = dict(table.get("items") or {})
    values = dict(items.get(code) or {})
    if price is None:
        values.pop("sale_price", None)
    else:
        values["sale_price"] = float(price)
    if values:
        items[code] = values
    else:
        items.pop(code, None)
    table["items"] = items
    settings.price_table = table
    settings.save()


def calc_config() -> CalcConfig:
    return CalcConfig.from_settings(LmSettings.get())
