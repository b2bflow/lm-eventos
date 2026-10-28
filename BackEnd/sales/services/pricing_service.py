from crm.models.lm_settings_model import LmSettings
from sales.catalog import (
    CATALOG_BY_CODE, COMPONENT_NAMES, METRO_PRICE, OPERATIONAL_COSTS, SOUND_SET_CODES, catalog_item_from_inventory,
    default_price_table, merge_price_table,
)
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


def price_settings() -> dict:
    """Valores gerais da calculadora (aba "Valores" em Configurações): preço do metro das torres,
    custos operacionais e preço de cada faixa de som. `default` = valor do catálogo."""
    table = effective_price_table()
    defaults = default_price_table()
    return {
        "metro_price": [
            {"line": line, "price": table["metro_price"].get(line), "default": price}
            for line, price in METRO_PRICE.items()
        ],
        "operational_costs": [
            {"code": code, "label": v["label"], "price": table["operational_costs"].get(code, v["price"]),
             "default": v["price"]}
            for code, v in OPERATIONAL_COSTS.items()
        ],
        "sound_tiers": [
            {"limit": limit, "code": code, "label": CATALOG_BY_CODE[code]["name"],
             "price": table["items"].get(code, {}).get("sale_price"),
             "default": defaults["items"][code]["sale_price"], "components": _components_text(code, table)}
            for limit, code in [*table["sound_tiers"], (None, "som_cerimonia")] if code in CATALOG_BY_CODE
        ],
    }


def _components_text(code: str, table: dict) -> str | None:
    """Peças do conjunto como saem no PDF ("4 Caixa de som ativa, 1 Microfone sem fio")."""
    pieces = (table.get("sound_sets") or {}).get(code)
    if not pieces:
        return None
    names = []
    for piece in pieces:
        item = CATALOG_BY_CODE.get(piece["code"]) or (table.get("extra_items") or {}).get(piece["code"]) or {}
        names.append(f"{piece['qty']:g} {COMPONENT_NAMES.get(piece['code'], item.get('name', piece['code']))}")
    return ", ".join(names)


def _money(value, label: str):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{label}: valor inválido.")
    try:
        price = float(str(value).replace(",", "."))
    except ValueError:
        raise ValueError(f"{label}: valor inválido.")
    if price < 0 or price != price or price in (float("inf"), float("-inf")):
        raise ValueError(f"{label}: o valor não pode ser negativo.")
    return round(price, 2)


def update_price_settings(data: dict) -> dict:
    """Grava os valores gerais em LmSettings.price_table. Valor vazio/None volta ao padrão do catálogo.
    Aceita {metro_price: {Q30: 15}, operational_costs: {carga: 300}, sound_tiers: {som_ate_150: 1300}}."""
    if not isinstance(data, dict):
        raise ValueError("Corpo inválido.")
    sections = {
        "metro_price": set(METRO_PRICE),
        "operational_costs": set(OPERATIONAL_COSTS),
        "sound_tiers": set(SOUND_SET_CODES),
    }
    for key, allowed in sections.items():
        values = data.get(key) or {}
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError(f"Valores desconhecidos em {key}.")
    # Valida tudo antes de gravar: ou entra tudo, ou nada
    parsed = {key: {code: _money(v, code) for code, v in (data.get(key) or {}).items()} for key in sections}

    settings = LmSettings.get()
    table = dict(settings.price_table or {})
    for key in ("metro_price", "operational_costs"):
        current = dict(table.get(key) or {})
        for code, price in parsed[key].items():
            if price is None:
                current.pop(code, None)
            else:
                current[code] = price
        table[key] = current
    items = dict(table.get("items") or {})
    for code, price in parsed["sound_tiers"].items():
        values = dict(items.get(code) or {})
        if price is None:
            values.pop("sale_price", None)
        else:
            values["sale_price"] = price
        if values:
            items[code] = values
        else:
            items.pop(code, None)
    table["items"] = items
    settings.price_table = table
    settings.save()
    return price_settings()


def calc_config() -> CalcConfig:
    return CalcConfig.from_settings(LmSettings.get())
