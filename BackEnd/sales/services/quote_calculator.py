"""Calculadora de proposta: função pura, sem banco.

Recebe entradas + tabela de preços (sales.catalog.merge_price_table) + configuração e devolve
linhas, totais e motivos de trava. Disponibilidade de estoque entra pronta em `availability`
({código: quantidade disponível no período, ou None quando o item não é contado}).

Modos: locação de porta (`calculate_porta`), corporativo (`calculate_corporativo`), social
(`calculate_social`, mesma fórmula do corporativo) e produto único (`calculate_produto_unico`).

Valores editados na proposta: `table["unit_overrides"]` ({código: preço unitário}) troca o preço
de um item só nesta proposta, e `apply_final_total` fixa o valor final. Baixar qualquer um dos
dois trava como desconto (a Erica aprova).
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import ceil

from sales.catalog import CATALOG_BY_CODE, OPERATIONAL_COSTS
from sales.formatting import format_brl

CENT = Decimal("0.01")

LOCK_MESSAGES = {
    "item_sem_preco": "Item sem preço cadastrado",
    "locacao_acima_1_semana": "Locação acima de 1 semana",
    "desconto": "Desconto ou ajuste negativo",
    "publico_acima_limite": "Público acima de 1.500 pessoas (exige visita técnica)",
    "acima_do_teto": "Total acima do teto de aprovação",
    "estoque_insuficiente": "Estoque insuficiente na data",
    "custo_projeto": "Custo de projeto informado",
    "reuniao_erica": "Social fora do padrão da SDR: reunião com a Erica",
}


def fmt_qty(value) -> str:
    """Quantidade sem casas desnecessárias: 83.0 -> '83', 2.5 -> '2,5'."""
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}".replace(".", ",")


def non_negative(value, label: str) -> Decimal:
    """Valor digitado na calculadora (frete, custo de projeto, desconto, quantidade): número finito
    e não negativo. Frete negativo, por exemplo, viraria um desconto escondido e sem trava."""
    try:
        number = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor inválido em {label}.")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} não pode ser negativo.")
    return number


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class CalcConfig:
    approval_ceiling: Decimal = Decimal("15000")
    invoice_rate: Decimal = Decimal("0.15")
    margin_levels: tuple = (Decimal("0.20"), Decimal("0.35"), Decimal("0.50"))
    max_guests_without_visit: int = 1500
    base_period_days: int = 7
    social_max_guests: int = 200
    social_max_total: Decimal = Decimal("6000")

    @classmethod
    def from_settings(cls, settings) -> "CalcConfig":
        return cls(
            approval_ceiling=Decimal(str(settings.approval_ceiling)),
            invoice_rate=Decimal(str(settings.invoice_rate)),
            margin_levels=tuple(Decimal(str(m)) for m in settings.margin_levels),
            max_guests_without_visit=int(settings.max_guests_without_visit),
            social_max_guests=int(getattr(settings, "social_max_guests", None) or 200),
            social_max_total=Decimal(str(getattr(settings, "social_max_total", None) or 6000)),
        )


@dataclass
class QuoteResult:
    mode: str
    lines: list = field(default_factory=list)
    operational: list = field(default_factory=list)
    items_total: Decimal = Decimal("0")
    costs_total: Decimal = Decimal("0")
    subtotal: Decimal = Decimal("0")
    margin_pct: Decimal = Decimal("0")
    margin_value: Decimal = Decimal("0")
    with_invoice: bool = False
    invoice_value: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    manual_adjustment: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    periods: int = 1
    lock_reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    pending_items: list = field(default_factory=list)
    requires_technical_visit: bool = False
    requires_meeting: bool = False  # social fora do padrão: reunião com a Erica
    calculated_total: Decimal | None = None  # total antes do valor final editado
    final_total_edited: bool = False

    @property
    def locked(self) -> bool:
        return bool(self.lock_reasons)

    def lock(self, code: str, detail: str | None = None):
        if not any(r["code"] == code and r.get("detail") == detail for r in self.lock_reasons):
            self.lock_reasons.append({"code": code, "message": LOCK_MESSAGES[code], "detail": detail})

    def to_dict(self) -> dict:
        def f(v):
            return float(v) if isinstance(v, Decimal) else v
        return {
            "mode": self.mode,
            "lines": [{k: f(v) for k, v in line.items()} for line in self.lines],
            "operational": [{k: f(v) for k, v in line.items()} for line in self.operational],
            "items_total": f(self.items_total), "costs_total": f(self.costs_total), "subtotal": f(self.subtotal),
            "margin_pct": f(self.margin_pct), "margin_value": f(self.margin_value),
            "with_invoice": self.with_invoice, "invoice_value": f(self.invoice_value),
            "discount": f(self.discount), "manual_adjustment": f(self.manual_adjustment),
            "total": f(self.total), "periods": self.periods, "locked": self.locked,
            "lock_reasons": self.lock_reasons, "warnings": self.warnings, "pending_items": self.pending_items,
            "requires_technical_visit": self.requires_technical_visit,
            "requires_meeting": self.requires_meeting,
            "calculated_total": f(self.calculated_total if self.calculated_total is not None else self.total),
            "final_total_edited": self.final_total_edited,
        }


# --- Linhas ---------------------------------------------------------------------------------

def unit_price(code: str, table: dict) -> Decimal | None:
    """Preço unitário por peça. Torres cobradas por metro: metragem cobrada x preço do metro da linha."""
    item = CATALOG_BY_CODE.get(code)
    if not item:
        raise ValueError(f"Item desconhecido: {code}")
    if item["billing_unit"] == "metro" and item.get("billed_length_m"):
        metro = table["metro_price"].get(item["line"])
        return None if metro is None else money(Decimal(str(metro)) * Decimal(str(item["billed_length_m"])))
    price = table["items"].get(code, {}).get("sale_price")
    return None if price is None else money(price)


def _add_line(result: QuoteResult, code: str, qty, table: dict, availability: dict | None, multiplier: int = 1,
              note: str | None = None, block: str | None = None):
    item = CATALOG_BY_CODE.get(code)
    if not item:
        raise ValueError(f"Item desconhecido: {code}")
    qty = non_negative(qty, f"Quantidade de {item['name']}")
    if qty == 0:
        return
    catalog_price = unit_price(code, table)
    price = catalog_price
    override = (table.get("unit_overrides") or {}).get(code)
    if override not in (None, ""):
        price = money(non_negative(override, f"Preço de {item['name']}"))
    line = {
        "code": code, "name": item["name"], "block": block or item.get("block") or "outros",
        # Torres cobradas por metro são pedidas em peças (o preço já é por peça)
        "qty": qty, "unit": "peça" if item["billing_unit"] == "metro" and item.get("billed_length_m") else item["billing_unit"],
        "unit_price": price if price is not None else None,
        "periods": multiplier, "subtotal": Decimal("0"), "note": note or item.get("note"),
        "available": None, "shortage": False, "owned": item["owned"],
        "catalog_unit_price": catalog_price, "price_overridden": price != catalog_price,
    }
    if catalog_price is not None and price is not None and price < catalog_price:
        result.lock("desconto", f"{item['name']}: {format_brl(price)} (tabela {format_brl(catalog_price)})")
    if price is None:
        result.lock("item_sem_preco", item["name"])
        result.pending_items.append(item["name"])
    else:
        line["subtotal"] = money(price * qty * multiplier)

    if availability is not None and code in availability:
        available = availability[code]
        line["available"] = available
        if not item["owned"]:
            result.warnings.append(f"{item['name']}: terceirizado, confirmar disponibilidade com o fornecedor.")
        elif available is None:
            result.warnings.append(f"{item['name']}: quantidade em estoque ainda não contada.")
        elif qty > available:
            line["shortage"] = True
            result.lock("estoque_insuficiente", f"{item['name']}: pedido {fmt_qty(qty)}, disponível {fmt_qty(available)}")
    result.lines.append(line)


def rental_periods(pickup: date, return_date: date, base_days: int = 7) -> int:
    """Período base = 1 final de semana (até 7 dias entre retirada e devolução); acima disso, semanas."""
    if isinstance(pickup, datetime):
        pickup = pickup.date()
    if isinstance(return_date, datetime):
        return_date = return_date.date()
    days = (return_date - pickup).days
    if days < 0:
        raise ValueError("A devolução não pode ser antes da retirada.")
    return max(1, ceil(days / base_days))


# --- Locação de porta ----------------------------------------------------------------------

def calculate_porta(items: list[dict], pickup: date, return_date: date, table: dict,
                    config: CalcConfig | None = None, availability: dict | None = None) -> QuoteResult:
    """items: [{"code": "q30_torre_5m", "qty": 4}, ...]."""
    config = config or CalcConfig()
    result = QuoteResult(mode="porta")
    result.periods = rental_periods(pickup, return_date, config.base_period_days)
    if result.periods > 1:
        result.lock("locacao_acima_1_semana", f"{result.periods} semanas")
    note = f"x {result.periods} semanas" if result.periods > 1 else None
    for entry in items:
        _add_line(result, entry["code"], entry.get("qty", 0), table, availability, multiplier=result.periods, note=note)
    result.items_total = money(sum((line["subtotal"] for line in result.lines), Decimal("0")))
    result.subtotal = result.items_total
    result.total = result.items_total
    if result.total > config.approval_ceiling:
        result.lock("acima_do_teto", f"R$ {result.total}")
    return result


def apply_final_total(result: QuoteResult, final_total, config: CalcConfig) -> QuoteResult:
    """Valor final editado na proposta (a Erica sobe ou desce conforme época, local e cliente).

    A diferença para o calculado vira ajuste manual, então o total do PDF bate com as linhas.
    Valor abaixo do calculado trava como desconto; acima do teto, como sempre."""
    result.calculated_total = result.total
    if final_total in (None, ""):
        return result
    final = money(non_negative(final_total, "Valor final"))
    if final <= 0:
        raise ValueError("O valor final precisa ser maior que zero.")
    difference = final - result.total
    if difference == 0:
        return result
    result.manual_adjustment = money(result.manual_adjustment + difference)
    result.total = final
    result.final_total_edited = True
    if difference < 0:
        result.lock("desconto", f"Valor final {format_brl(final)} (calculado {format_brl(result.calculated_total)})")
    # O teto vale para o valor que vai na proposta, não para o calculado
    result.lock_reasons = [r for r in result.lock_reasons if r["code"] != "acima_do_teto"]
    if result.total > config.approval_ceiling:
        result.lock("acima_do_teto", f"R$ {result.total}")
    return result


# --- Corporativo ---------------------------------------------------------------------------

@dataclass
class CorporateInput:
    guests: int
    style: str = ""
    band: str = "nenhuma"  # nenhuma | voz_violao | completa
    dance_floor: bool = False
    stage_m2: float = 0
    stage_covered: bool = True
    led_m2: float = 0
    led_technician: bool = False
    led_structure: int = 0
    backdrop: int = 0
    lights: dict = field(default_factory=dict)  # {"luz_moving_beam": 4, ...}
    extra_mics: int = 0
    tp: int = 0
    praticaveis: int = 0
    slide_passer: int = 0
    digital_mixer: int = 0
    pass_cable_m: float = 0
    extra_items: list = field(default_factory=list)  # [{"code", "qty"}] itens avulsos do catálogo
    operational: list = field(default_factory=list)  # chaves de OPERATIONAL_COSTS marcadas
    manual_freight: float = 0  # deslocamento fora de Goiânia
    project_cost: float = 0  # trava para aprovação
    margin: float = 0  # sem margem: a tabela já tem a margem da Erica
    with_invoice: bool = True
    discount: float = 0
    manual_adjustment: float = 0  # só admin (validado no serviço de proposta)


def sound_system_for(guests: int, table: dict) -> str:
    for limit, code in table["sound_tiers"]:
        if limit is None or guests <= limit:
            return code
    return table["sound_tiers"][-1][1]


def _check_margin(margin, config: CalcConfig) -> Decimal:
    """Sem margem é o padrão: os preços da tabela já têm a margem da Erica. Os níveis antigos
    continuam aceitos para recalcular propostas salvas com margem."""
    margin = Decimal(str(margin or 0))
    if margin != 0 and margin not in config.margin_levels:
        raise ValueError(f"Margem inválida. Use uma de: {', '.join(f'{m * 100:.0f}%' for m in config.margin_levels)}.")
    return margin


def _add_sound(result: QuoteResult, guests: int, band: str, dance_floor: bool, table: dict, config: CalcConfig,
               availability: dict | None):
    """Som pela faixa de público; sub duplo até 200 com banda ou pista; backline ou microfone pela banda."""
    sound = sound_system_for(guests, table)
    _add_line(result, sound, 1, table, availability, note=f"{guests} pessoas")
    if guests > config.max_guests_without_visit:
        result.requires_technical_visit = True
        result.lock("publico_acima_limite", f"{guests} pessoas")
    if guests <= 200 and (band != "nenhuma" or dance_floor):
        _add_line(result, "som_sub_duplo", 1, table, availability, note="Banda ou pista até 200 pessoas")
    if band == "completa":
        _add_line(result, "som_backline", 1, table, availability)
        result.warnings.append("Banda completa: a Erica revisa o rider.")
    elif band == "voz_violao":
        _add_line(result, "som_mic_sem_fio", 1, table, availability, note="Voz e violão")


def _add_lights(result: QuoteResult, lights: dict, table: dict, availability: dict | None):
    for code, qty in (lights or {}).items():
        if CATALOG_BY_CODE.get(code, {}).get("block") != "iluminacao":
            raise ValueError(f"Item de iluminação inválido: {code}")
        _add_line(result, code, qty, table, availability)


def _add_operational(result: QuoteResult, keys: list, table: dict, manual_freight=0, project_cost=0):
    manual_freight = non_negative(manual_freight, "Frete manual")
    project_cost = non_negative(project_cost, "Custo de projeto")
    for key in keys or []:
        if key not in OPERATIONAL_COSTS:
            raise ValueError(f"Custo operacional inválido: {key}")
        price = money(table["operational_costs"].get(key, OPERATIONAL_COSTS[key]["price"]))
        result.operational.append({"code": key, "name": OPERATIONAL_COSTS[key]["label"], "subtotal": price})
    if manual_freight:
        result.operational.append({"code": "frete_manual", "name": "Deslocamento fora de Goiânia", "subtotal": money(manual_freight)})
    if project_cost:
        result.operational.append({"code": "projeto", "name": "Custo de projeto", "subtotal": money(project_cost)})
        result.lock("custo_projeto", f"R$ {money(project_cost)}")


def _finalize(result: QuoteResult, config: CalcConfig, margin: Decimal = Decimal("0"), with_invoice: bool = False,
              discount=0, manual_adjustment=0):
    """total = (itens + custos operacionais) x (1 + margem) x 1,15 (com nota) - desconto + ajuste manual."""
    result.items_total = money(sum((line["subtotal"] for line in result.lines), Decimal("0")))
    result.costs_total = money(sum((c["subtotal"] for c in result.operational), Decimal("0")))
    result.subtotal = result.items_total + result.costs_total
    result.margin_pct = margin
    with_margin = money(result.subtotal * (1 + margin))
    result.margin_value = with_margin - result.subtotal
    result.with_invoice = bool(with_invoice)
    after_invoice = money(with_margin * (1 + config.invoice_rate)) if with_invoice else with_margin
    result.invoice_value = after_invoice - with_margin
    result.discount = money(non_negative(discount, "Desconto"))
    result.manual_adjustment = money(manual_adjustment)
    if result.discount > 0:
        result.lock("desconto", f"R$ {result.discount}")
    if result.manual_adjustment < 0:
        result.lock("desconto", f"Ajuste manual R$ {result.manual_adjustment}")
    result.total = money(after_invoice - result.discount + result.manual_adjustment)
    if result.total > config.approval_ceiling:
        result.lock("acima_do_teto", f"R$ {result.total}")


def calculate_corporativo(data: CorporateInput, table: dict, config: CalcConfig | None = None,
                          availability: dict | None = None) -> QuoteResult:
    config = config or CalcConfig()
    result = QuoteResult(mode="corporativo")
    if data.guests <= 0:
        raise ValueError("Informe o número de pessoas.")
    margin = _check_margin(data.margin, config)

    _add_sound(result, data.guests, data.band, data.dance_floor, table, config, availability)
    if data.extra_mics:
        _add_line(result, "som_mic_sem_fio", data.extra_mics, table, availability, note="Adicionais")
    if data.digital_mixer:
        _add_line(result, "som_mesa_digital", data.digital_mixer, table, availability)

    # Palco, vídeo e iluminação
    if data.stage_m2:
        _add_line(result, "palco_forrado" if data.stage_covered else "palco_sem_forracao", data.stage_m2, table, availability)
    if data.praticaveis:
        _add_line(result, "palco_praticavel_2x1", data.praticaveis, table, availability)
    if data.backdrop:
        _add_line(result, "palco_backdrop", data.backdrop, table, availability)
    if data.pass_cable_m:
        _add_line(result, "palco_passa_cabo", data.pass_cable_m, table, availability)
    if data.led_m2:
        _add_line(result, "video_led_corporativo", data.led_m2, table, availability)
    if data.led_technician:
        _add_line(result, "video_tecnico_led", 1, table, availability)
    if data.led_structure:
        _add_line(result, "video_estrutura_led", data.led_structure, table, availability)
    if data.tp:
        _add_line(result, "video_tp", data.tp, table, availability)
    if data.slide_passer:
        _add_line(result, "video_passador_slides", data.slide_passer, table, availability)
    _add_lights(result, data.lights, table, availability)
    for entry in data.extra_items or []:
        _add_line(result, entry["code"], entry.get("qty", 0), table, availability)

    _add_operational(result, data.operational, table, data.manual_freight, data.project_cost)
    _finalize(result, config, margin, data.with_invoice, data.discount, data.manual_adjustment)
    return result


# --- Social --------------------------------------------------------------------------------

@dataclass
class SocialInput:
    guests: int
    style: str = ""
    band: str = "nenhuma"  # nenhuma | voz_violao | completa
    dance_floor: bool = True
    structure: str = "nenhuma"  # nenhuma | chave de STRUCTURE_KITS (gol_3x4, grid_4x4x3)
    stage_m2: float = 0
    stage_covered: bool = True
    praticaveis: int = 0
    backdrop: int = 0
    led_m2: float = 0  # R$ 250/m² com técnico embutido
    led_structure: int = 0
    lights: dict = field(default_factory=dict)  # pontual, PAR 38, fumaça, piso de microlâmpadas...
    ceremony_sound: bool = False  # 4 caixas ativas, pedestais, mesa e microfone
    extra_mics: int = 0
    dj: bool = False
    extra_items: list = field(default_factory=list)
    operational: list = field(default_factory=list)
    manual_freight: float = 0
    project_cost: float = 0
    has_project: bool = False  # cliente mandou projeto: reunião com a Erica
    competitor_quote: bool = False  # cliente mandou orçamento concorrente: reunião com a Erica
    margin: float = 0  # sem margem: a tabela já tem a margem da Erica
    with_invoice: bool = True
    discount: float = 0
    manual_adjustment: float = 0


def _add_kit(result: QuoteResult, kit_key: str, table: dict, availability: dict | None):
    kit = (table.get("kits") or {}).get(kit_key)
    if not kit:
        raise ValueError(f"Estrutura inválida: {kit_key}")
    for piece in kit["pieces"]:
        _add_line(result, piece["code"], piece["qty"], table, availability, note=kit["label"], block="estrutura")
        result.lines[-1]["kit"] = kit["label"]


def calculate_social(data: SocialInput, table: dict, config: CalcConfig | None = None,
                     availability: dict | None = None) -> QuoteResult:
    """Mesma fórmula do corporativo. Acima de 200 convidados, acima de R$ 6.000, com projeto ou com
    orçamento concorrente, a proposta trava e vira reunião com a Erica."""
    config = config or CalcConfig()
    result = QuoteResult(mode="social")
    if data.guests <= 0:
        raise ValueError("Informe o número de convidados.")
    margin = _check_margin(data.margin, config)

    if data.structure and data.structure != "nenhuma":
        _add_kit(result, data.structure, table, availability)
    _add_sound(result, data.guests, data.band, data.dance_floor, table, config, availability)
    if data.ceremony_sound:
        _add_line(result, "som_cerimonia", 1, table, availability)
    if data.extra_mics:
        _add_line(result, "som_mic_sem_fio", data.extra_mics, table, availability, note="Adicionais")
    if data.stage_m2:
        _add_line(result, "palco_forrado" if data.stage_covered else "palco_sem_forracao", data.stage_m2, table, availability)
    if data.praticaveis:
        _add_line(result, "palco_praticavel_2x1", data.praticaveis, table, availability)
    if data.backdrop:
        _add_line(result, "palco_backdrop", data.backdrop, table, availability)
    if data.led_m2:
        _add_line(result, "video_led_social", data.led_m2, table, availability)
    if data.led_structure:
        _add_line(result, "video_estrutura_led", data.led_structure, table, availability)
    _add_lights(result, data.lights, table, availability)
    for entry in data.extra_items or []:
        _add_line(result, entry["code"], entry.get("qty", 0), table, availability)

    operational = list(data.operational or [])
    if data.dj and "dj" not in operational:
        operational.append("dj")
    _add_operational(result, operational, table, data.manual_freight, data.project_cost)
    _finalize(result, config, margin, data.with_invoice, data.discount, data.manual_adjustment)

    if data.guests > config.social_max_guests:
        result.lock("reuniao_erica", f"Acima de {config.social_max_guests} convidados")
    if result.total > config.social_max_total:
        result.lock("reuniao_erica", f"Acima de {format_brl(config.social_max_total)}")
    if data.has_project or data.project_cost:
        result.lock("reuniao_erica", "Cliente tem projeto")
    if data.competitor_quote:
        result.lock("reuniao_erica", "Cliente tem orçamento concorrente")
    result.requires_meeting = any(r["code"] == "reuniao_erica" for r in result.lock_reasons)
    return result


# --- Produto único ---------------------------------------------------------------------------

@dataclass
class SingleProductInput:
    items: list = field(default_factory=list)  # [{"code", "qty"}]
    delivery: str = "retirada"  # retirada (na LM, sem custo) | entrega
    assembly: bool = False
    assembly_people: int = 0
    assembly_days: int = 1
    manual_freight: float = 0
    discount: float = 0
    manual_adjustment: float = 0


PRATICAVEL_CODES = {"palco_praticavel_2x1"}


def calculate_produto_unico(data: SingleProductInput, table: dict, config: CalcConfig | None = None,
                            availability: dict | None = None, periods: int = 1) -> QuoteResult:
    """Preço da tabela, sem margem. Retirada na LM sem custo; entrega soma frete + carga e descarga
    (só praticável: entrega fixa ida e volta); montagem soma mão de obra avulsa por pessoa/dia."""
    config = config or CalcConfig()
    result = QuoteResult(mode="produto_unico", periods=max(1, int(periods or 1)))
    items = [e for e in data.items or [] if non_negative(e.get("qty"), "Quantidade") > 0]
    if not items:
        raise ValueError("Informe ao menos um item.")
    if data.delivery not in ("retirada", "entrega"):
        raise ValueError("Forma de entrega inválida.")
    if result.periods > 1:
        result.lock("locacao_acima_1_semana", f"{result.periods} semanas")
    note = f"x {result.periods} semanas" if result.periods > 1 else None
    for entry in items:
        _add_line(result, entry["code"], entry["qty"], table, availability, multiplier=result.periods, note=note)

    costs = table["operational_costs"]
    if data.delivery == "entrega":
        if {e["code"] for e in items} <= PRATICAVEL_CODES:
            result.operational.append({"code": "entrega_praticavel", "subtotal": money(costs["entrega_praticavel"]),
                                       "name": "Entrega de praticável (ida e volta)"})
        else:
            for key in ("frete", "carga", "descarga"):
                result.operational.append({"code": key, "name": OPERATIONAL_COSTS[key]["label"], "subtotal": money(costs[key])})
    else:
        result.warnings.append("Retirada na LM: sem custo de entrega.")
    if data.assembly:
        people, days = int(data.assembly_people or 0), max(1, int(data.assembly_days or 1))
        if people <= 0:
            raise ValueError("Informe quantas pessoas fazem a montagem.")
        price = money(costs["mao_de_obra_avulsa"])
        result.operational.append({
            "code": "mao_de_obra_avulsa", "subtotal": money(price * people * days),
            "name": f"Montagem: {people} pessoa(s) x {days} dia(s)",
        })
    manual_freight = non_negative(data.manual_freight, "Frete manual")
    if manual_freight:
        result.operational.append({"code": "frete_manual", "name": "Deslocamento fora de Goiânia", "subtotal": money(manual_freight)})

    _finalize(result, config, discount=data.discount, manual_adjustment=data.manual_adjustment)
    floor_only = {e["code"] for e in items} == {"luz_piso_microlampadas"}
    if floor_only and result.items_total < Decimal("1300"):
        result.warnings.append("Piso de microlâmpadas sozinho: mínimo de cerca de R$ 1.300.")
    return result
