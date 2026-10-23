"""Calculadora de proposta (regra de negócio pura, sem banco)."""
from datetime import date
from decimal import Decimal

import pytest

from sales.catalog import CATALOG, SOCIAL_BASIC_PACKAGE, merge_price_table
from sales.services.quote_calculator import (
    CalcConfig, CorporateInput, SingleProductInput, SocialInput, calculate_corporativo, calculate_porta,
    calculate_produto_unico, calculate_social, rental_periods, sound_system_for, unit_price,
)

TABLE = merge_price_table(None)
SAT, SUN = date(2026, 10, 24), date(2026, 10, 25)


def porta(items, pickup=SAT, ret=SUN, **kw):
    return calculate_porta(items, pickup, ret, TABLE, **kw)


def codes(result):
    return {line["code"]: line for line in result.lines}


def lock_codes(result):
    return {r["code"] for r in result.lock_reasons}


# --- Locação de porta ----------------------------------------------------------------------

@pytest.mark.parametrize("code,price", [
    ("q30_torre_5m", "75.00"),
    ("q30_torre_4m", "60.00"),
    ("q30_torre_3m", "45.00"),
    ("q30_torre_2_5m", "45.00"),   # 2,5 m conta como 3 m
    ("q30_torre_2m", "30.00"),
    ("q30_torre_1m", "20.00"),
    ("q30_torre_0_5m", "20.00"),
    ("q30_adaptador_10", "20.00"),
    ("q30_cubo_5_faces", "20.00"),
    ("q30_cumeeira", "60.00"),
    ("q30_sleeve", "50.00"),
    ("q30_sapata", "15.00"),
    ("q15_torre_3m", "39.00"),
    ("q15_torre_2_5m", "39.00"),   # 2,5 m conta como 3 m
    ("q15_torre_2m", "26.00"),
    ("q15_torre_1m", "13.00"),
    ("q15_cubo", "13.00"),
    ("q15_sapata", "13.00"),
    ("q15_cumeeira", "20.00"),     # exceção Q15
])
def test_porta_unit_prices(code, price):
    assert unit_price(code, TABLE) == Decimal(price)


def test_porta_weekend_total():
    result = porta([{"code": "q30_torre_5m", "qty": 4}, {"code": "q30_cubo_5_faces", "qty": 4}, {"code": "q30_sapata", "qty": 4}])
    assert result.total == Decimal("440.00")  # 4x75 + 4x20 + 4x15
    assert result.periods == 1 and not result.locked


def test_rental_periods():
    assert rental_periods(date(2026, 10, 23), date(2026, 10, 26)) == 1
    assert rental_periods(date(2026, 10, 19), date(2026, 10, 26)) == 1   # 7 dias = 1 período
    assert rental_periods(date(2026, 10, 16), date(2026, 10, 26)) == 2   # 10 dias
    with pytest.raises(ValueError):
        rental_periods(SUN, SAT)


def test_ten_days_multiplies_and_locks_for_approval():
    result = porta([{"code": "q30_torre_5m", "qty": 2}], pickup=date(2026, 10, 16), ret=date(2026, 10, 26))
    assert result.periods == 2
    assert result.total == Decimal("300.00")
    assert "locacao_acima_1_semana" in lock_codes(result)


def test_item_without_price_locks_and_lists_pending():
    result = porta([{"code": "q30_torre_3m", "qty": 1}, {"code": "ac_talha_10m", "qty": 2}, {"code": "ac_cubo_22", "qty": 4}])
    assert "item_sem_preco" in lock_codes(result)
    assert set(result.pending_items) == {"Talha 10 m", "Cubo 22°"}
    assert result.total == Decimal("45.00")


def test_edited_price_table_is_used():
    table = merge_price_table({"metro_price": {"Q30": 16}, "items": {"ac_talha_10m": {"sale_price": 120}}})
    assert unit_price("q30_torre_5m", table) == Decimal("80.00")
    result = calculate_porta([{"code": "ac_talha_10m", "qty": 1}], SAT, SUN, table)
    assert result.total == Decimal("120.00") and not result.locked


def test_porta_stock_shortage_locks():
    result = porta([{"code": "q30_torre_5m", "qty": 120}], availability={"q30_torre_5m": 113})
    assert codes(result)["q30_torre_5m"]["shortage"] is True
    assert "estoque_insuficiente" in lock_codes(result)


def test_porta_above_ceiling_locks():
    result = porta([{"code": "q30_torre_5m", "qty": 113}, {"code": "q30_torre_4m", "qty": 70},
                    {"code": "q30_torre_3m", "qty": 127}, {"code": "q30_cubo_5_faces", "qty": 215}])
    assert result.total > Decimal("15000")
    assert "acima_do_teto" in lock_codes(result)


# --- Corporativo -----------------------------------------------------------------------------

@pytest.mark.parametrize("guests,expected", [
    (80, "som_ate_150"), (150, "som_ate_150"), (151, "som_150_200"), (200, "som_150_200"),
    (201, "som_200_500"), (300, "som_200_500"), (500, "som_200_500"), (501, "som_500_1500"),
    (1500, "som_500_1500"), (1501, "som_acima_1500"),
])
def test_sound_by_audience(guests, expected):
    assert sound_system_for(guests, TABLE) == expected


def test_corporate_formula_with_margin_and_invoice():
    data = CorporateInput(guests=100, stage_m2=12, lights={"luz_par_led": 8}, operational=["carga", "descarga"],
                          margin=0.35, with_invoice=True)
    result = calculate_corporativo(data, TABLE)
    # itens: som 1300 + palco 12x95=1140 + 8 par LED x50=400 = 2840; custos: 300+250 = 550
    assert result.items_total == Decimal("2840.00") and result.costs_total == Decimal("550.00")
    expected = (Decimal("3390") * Decimal("1.35")).quantize(Decimal("0.01")) * Decimal("1.15")
    assert result.total == expected.quantize(Decimal("0.01"))  # 3390 x 1,35 x 1,15 = 5262,98
    assert result.total == Decimal("5262.98")
    assert not result.locked


def test_corporate_without_invoice_skips_115():
    data = CorporateInput(guests=100, margin=0.20, with_invoice=False)
    assert calculate_corporativo(data, TABLE).total == Decimal("1560.00")  # 1300 x 1,20


def test_band_microphone_stays_apart_from_extra_mics():
    # Voz e violão soma 1 microfone (regra da LM); os extras pedidos são outra linha, com o mesmo preço
    result = calculate_corporativo(CorporateInput(guests=2, band="voz_violao", extra_mics=2), TABLE)
    mics = [l for l in result.lines if l["code"] == "som_mic_sem_fio"]
    assert [(l["name"], l["qty"]) for l in mics] == [("Microfone sem fio (voz e violão)", 1),
                                                     ("Microfone sem fio adicional", 2)]
    assert sum(l["subtotal"] for l in mics) == Decimal("450.00")
    assert result.items_total == sum(l["subtotal"] for l in result.lines)


def test_counted_items_need_whole_quantities():
    with pytest.raises(ValueError, match="inteiro"):
        calculate_corporativo(CorporateInput(guests=50, extra_mics=2.5), TABLE)
    with pytest.raises(ValueError, match="inteiro"):
        porta([{"code": "q30_torre_5m", "qty": 1.5}])  # torre cobrada por metro, mas pedida em peças
    # m² e metro aceitam fração
    stage = calculate_corporativo(CorporateInput(guests=50, stage_m2=2.5, pass_cable_m=7.5), TABLE)
    assert codes(stage)["palco_forrado"]["qty"] == Decimal("2.5") and codes(stage)["palco_passa_cabo"]["qty"] == Decimal("7.5")


def test_stock_check_adds_up_lines_of_the_same_item():
    # 1 da banda + 2 extras = 3 pedidos; com 2 no estoque, cada linha sozinha passava
    result = calculate_corporativo(CorporateInput(guests=2, band="voz_violao", extra_mics=2), TABLE,
                                   availability={"som_mic_sem_fio": 2})
    assert "estoque_insuficiente" in lock_codes(result)
    assert any("pedido 3, disponível 2" in (r["detail"] or "") for r in result.lock_reasons)
    ok = calculate_corporativo(CorporateInput(guests=2, band="voz_violao", extra_mics=2), TABLE,
                               availability={"som_mic_sem_fio": 3})
    assert "estoque_insuficiente" not in lock_codes(ok)


def test_sub_and_band_rules():
    full_band = calculate_corporativo(CorporateInput(guests=180, band="completa"), TABLE)
    assert {"som_150_200", "som_sub_duplo", "som_backline"} <= set(codes(full_band))
    assert any("rider" in w for w in full_band.warnings)

    voice = calculate_corporativo(CorporateInput(guests=120, band="voz_violao"), TABLE)
    assert codes(voice)["som_mic_sem_fio"]["qty"] == 1 and "som_sub_duplo" in codes(voice)

    big = calculate_corporativo(CorporateInput(guests=300, dance_floor=True), TABLE)
    assert "som_sub_duplo" not in codes(big)  # sub já incluso a partir de 200

    no_band = calculate_corporativo(CorporateInput(guests=100), TABLE)
    assert "som_sub_duplo" not in codes(no_band)


def test_corporate_locks_above_1500_people_and_requires_visit():
    result = calculate_corporativo(CorporateInput(guests=2000, margin=0.20, with_invoice=False), TABLE)
    assert result.requires_technical_visit is True
    assert "publico_acima_limite" in lock_codes(result)


def test_corporate_locks_above_ceiling():
    data = CorporateInput(guests=800, led_m2=24, stage_m2=40, lights={"luz_moving_beam": 12},
                          operational=["carga", "montagem", "desmontagem", "descarga", "frete", "alimentacao"],
                          margin=0.50)
    result = calculate_corporativo(data, TABLE)
    assert result.total > Decimal("15000") and "acima_do_teto" in lock_codes(result)

    lower_ceiling = CalcConfig(approval_ceiling=Decimal("1000"))
    small = calculate_corporativo(CorporateInput(guests=100, margin=0.20, with_invoice=False), TABLE, lower_ceiling)
    assert "acima_do_teto" in lock_codes(small)


def test_discount_negative_adjustment_and_project_lock():
    assert "desconto" in lock_codes(calculate_corporativo(CorporateInput(guests=100, discount=100), TABLE))
    assert "desconto" in lock_codes(calculate_corporativo(CorporateInput(guests=100, manual_adjustment=-50), TABLE))
    positive = calculate_corporativo(CorporateInput(guests=100, margin=0.20, with_invoice=False, manual_adjustment=40), TABLE)
    assert positive.total == Decimal("1600.00") and not positive.locked
    assert "custo_projeto" in lock_codes(calculate_corporativo(CorporateInput(guests=100, project_cost=800), TABLE))


def test_invalid_margin_rejected():
    with pytest.raises(ValueError):
        calculate_corporativo(CorporateInput(guests=100, margin=0.10), TABLE)


def test_led_is_outsourced_warning_not_stock_lock():
    result = calculate_corporativo(CorporateInput(guests=100, led_m2=6), TABLE,
                                   availability={"video_led_corporativo": 0, "som_ate_150": None})
    assert "estoque_insuficiente" not in lock_codes(result)
    assert any("fornecedor" in w for w in result.warnings)
    assert any("não contada" in w for w in result.warnings)


def test_basic_wedding_operational_costs_sum_3550():
    # Teste de sanidade da seção 5.3
    data = CorporateInput(guests=100, operational=["carga", "montagem", "desmontagem", "descarga", "frete", "alimentacao"])
    assert calculate_corporativo(data, TABLE).costs_total == Decimal("3550.00")


def test_catalog_codes_are_unique():
    all_codes = [item["code"] for item in CATALOG]
    assert len(all_codes) == len(set(all_codes))


# --- Social ----------------------------------------------------------------------------------

def meeting_details(result):
    return {r["detail"] for r in result.lock_reasons if r["code"] == "reuniao_erica"}


def test_social_same_formula_as_corporate_and_led_250_with_technician():
    data = SocialInput(guests=100, dance_floor=False, led_m2=6, operational=["carga", "descarga"],
                       margin=0.35, with_invoice=True)
    result = calculate_social(data, TABLE)
    led = codes(result)["video_led_social"]
    assert led["unit_price"] == Decimal("250.00") and led["subtotal"] == Decimal("1500.00")
    assert "video_tecnico_led" not in codes(result)  # técnico embutido no social
    # itens: som 1300 + LED 1500 = 2800; custos 550 -> 3350 x 1,35 = 4522,50 x 1,15 = 5200,88
    assert result.subtotal == Decimal("3350.00")
    assert result.total == Decimal("5200.88")
    assert not result.locked and not result.requires_meeting


def test_social_dj_lights_ceremony_and_floor():
    data = SocialInput(guests=120, dj=True, ceremony_sound=True, margin=0.20, with_invoice=False,
                       lights={"luz_pontual": 4, "luz_par_38": 6, "luz_fumaca": 1, "luz_piso_microlampadas": 9})
    result = calculate_social(data, TABLE)
    lines = codes(result)
    assert {"som_ate_150", "som_sub_duplo", "som_cerimonia"} <= set(lines)  # pista por padrão soma o sub
    assert lines["luz_pontual"]["subtotal"] == Decimal("320.00")
    assert lines["luz_par_38"]["subtotal"] == Decimal("300.00")
    assert lines["luz_fumaca"]["subtotal"] == Decimal("120.00")
    assert lines["luz_piso_microlampadas"]["subtotal"] == Decimal("450.00")
    assert [c["code"] for c in result.operational] == ["dj"]
    assert result.costs_total == Decimal("700.00")


def test_social_structure_kit_uses_q30_table():
    result = calculate_social(SocialInput(guests=80, structure="gol_3x4", dance_floor=False), TABLE)
    kit = [l for l in result.lines if l["block"] == "estrutura"]
    # 2 torres 3 m (45) + 1 torre 4 m (60) + 2 cubos (20) + 2 sapatas (15) = 220
    assert sum(l["subtotal"] for l in kit) == Decimal("220.00")
    with pytest.raises(ValueError):
        calculate_social(SocialInput(guests=80, structure="tenda"), TABLE)


def test_social_basic_package():
    result = calculate_social(SocialInput(guests=150, **SOCIAL_BASIC_PACKAGE), TABLE)
    lines = codes(result)
    assert {"q30_torre_3m", "video_led_social", "som_ate_150", "luz_par_led"} <= set(lines)
    assert lines["video_led_social"]["qty"] == 6
    assert "dj" in {c["code"] for c in result.operational}
    assert result.items_total == Decimal("4340.00")
    assert result.costs_total == Decimal("4250.00")  # 3.550 do casamento básico + DJ
    # Com a operação completa, o pacote passa do teto social padrão (R$ 6.000): pendência com a Erica.
    assert meeting_details(result) == {"Acima de R$ 6.000,00"}


@pytest.mark.parametrize("data,detail", [
    (SocialInput(guests=201, dance_floor=False, margin=0.20, with_invoice=False), "Acima de 200 convidados"),
    (SocialInput(guests=100, has_project=True, margin=0.20, with_invoice=False), "Cliente tem projeto"),
    (SocialInput(guests=100, competitor_quote=True, margin=0.20, with_invoice=False), "Cliente tem orçamento concorrente"),
    (SocialInput(guests=150, led_m2=20, margin=0.20, with_invoice=False), "Acima de R$ 6.000,00"),
])
def test_social_locks_become_meeting_with_erica(data, detail):
    result = calculate_social(data, TABLE)
    assert result.locked and result.requires_meeting
    assert detail in meeting_details(result)


def test_social_limits_are_configurable():
    config = CalcConfig(social_max_guests=300, social_max_total=Decimal("20000"))
    result = calculate_social(SocialInput(guests=250, led_m2=20, margin=0.20, with_invoice=False), TABLE, config)
    assert not result.requires_meeting


# --- Produto único ---------------------------------------------------------------------------

def test_single_product_pickup_at_lm_has_no_extra_cost():
    result = calculate_produto_unico(SingleProductInput(items=[{"code": "palco_praticavel_2x1", "qty": 4}]), TABLE)
    assert result.total == Decimal("600.00") and result.costs_total == 0
    assert result.margin_pct == 0 and not result.with_invoice  # preço da tabela, sem margem nem nota
    assert not result.locked


def test_single_product_praticavel_delivery_is_150_round_trip():
    data = SingleProductInput(items=[{"code": "palco_praticavel_2x1", "qty": 4}], delivery="entrega")
    result = calculate_produto_unico(data, TABLE)
    assert [c["code"] for c in result.operational] == ["entrega_praticavel"]
    assert result.total == Decimal("750.00")


def test_single_product_delivery_adds_freight_loading_unloading_and_assembly():
    data = SingleProductInput(items=[{"code": "luz_moving_beam", "qty": 4}], delivery="entrega",
                              assembly=True, assembly_people=2, assembly_days=1)
    result = calculate_produto_unico(data, TABLE)
    costs = {c["code"]: c["subtotal"] for c in result.operational}
    assert costs == {"frete": Decimal("300.00"), "carga": Decimal("300.00"), "descarga": Decimal("250.00"),
                     "mao_de_obra_avulsa": Decimal("450.00")}
    assert result.total == Decimal("600.00") + Decimal("1300.00")
    with pytest.raises(ValueError):
        calculate_produto_unico(SingleProductInput(items=[{"code": "luz_par_led", "qty": 1}], assembly=True), TABLE)


def test_single_product_stock_long_rental_and_missing_price_lock():
    result = calculate_produto_unico(SingleProductInput(items=[{"code": "palco_passa_cabo", "qty": 8}]), TABLE,
                                     availability={"palco_passa_cabo": 5}, periods=2)
    assert {"estoque_insuficiente", "locacao_acima_1_semana"} <= lock_codes(result)
    assert result.total == Decimal("480.00")  # 8 x 30 x 2 semanas
    no_price = calculate_produto_unico(SingleProductInput(items=[{"code": "ac_talha_5m", "qty": 1}]), TABLE)
    assert "item_sem_preco" in lock_codes(no_price)
    with pytest.raises(ValueError):
        calculate_produto_unico(SingleProductInput(items=[]), TABLE)


def test_single_product_floor_alone_warns_minimum():
    result = calculate_produto_unico(SingleProductInput(items=[{"code": "luz_piso_microlampadas", "qty": 9}]), TABLE)
    assert any("mínimo" in w for w in result.warnings)


# --- Serviços opcionais (Som, Palco e vídeo, Iluminação) -------------------------------------

ALL_SECTIONS = dict(stage_m2=10, backdrop=1, pass_cable_m=5, led_m2=4, tp=1, extra_mics=2,
                    lights={"luz_par_led": 4}, margin=0, with_invoice=False)


def test_corporate_sections_off_add_nothing():
    off = dict(sound_enabled=False, stage_video_enabled=False, lighting_enabled=False)
    result = calculate_corporativo(CorporateInput(guests=100, digital_mixer=1, **ALL_SECTIONS, **off), TABLE)
    assert result.lines == []
    assert result.total == Decimal("0.00")


def test_corporate_only_lighting():
    result = calculate_corporativo(CorporateInput(guests=100, sound_enabled=False, stage_video_enabled=False,
                                                  **ALL_SECTIONS), TABLE)
    assert set(codes(result)) == {"luz_par_led"}


def test_corporate_sound_on_brings_system_mics_and_mixer():
    result = calculate_corporativo(CorporateInput(guests=100, digital_mixer=1, stage_video_enabled=False,
                                                  lighting_enabled=False, **ALL_SECTIONS), TABLE)
    assert set(codes(result)) == {"som_ate_150", "som_mic_sem_fio", "som_mesa_digital"}


def test_sections_default_on_for_old_proposals():
    result = calculate_corporativo(CorporateInput(guests=100, **ALL_SECTIONS), TABLE)
    assert {"som_ate_150", "palco_forrado", "palco_backdrop", "video_tp", "luz_par_led"} <= set(codes(result))


def test_visit_lock_applies_without_sound():
    result = calculate_corporativo(CorporateInput(guests=1600, sound_enabled=False, lights={"luz_par_led": 1}), TABLE)
    assert "publico_acima_limite" in lock_codes(result)
    assert result.requires_technical_visit


def test_social_sound_off_skips_ceremony_and_system():
    result = calculate_social(SocialInput(guests=100, ceremony_sound=True, sound_enabled=False, led_m2=4,
                                          margin=0, with_invoice=False), TABLE)
    assert set(codes(result)) == {"video_led_social"}
