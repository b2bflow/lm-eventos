"""Calculadora sem margem, preço editado por item e valor final editado (reunião com o Marcelo)."""
from datetime import date
from decimal import Decimal

import pytest

from crm.models.custumer_model import Customer
from sales.catalog import merge_price_table
from sales.services.quote_calculator import (
    CalcConfig, CorporateInput, apply_final_total, calculate_corporativo, calculate_porta,
)

SAT, SUN = date(2026, 10, 24), date(2026, 10, 25)
PROPOSALS = "/api/v1/sales/proposals/"


def table(**overrides):
    t = merge_price_table(None)
    t["unit_overrides"] = overrides
    return t


def lock_codes(result):
    return {r["code"] for r in result.lock_reasons}


def test_event_has_no_margin_by_default_but_keeps_invoice():
    result = calculate_corporativo(CorporateInput(guests=100), table())
    assert result.margin_pct == 0 and result.margin_value == 0
    assert result.total == (result.subtotal * Decimal("1.15")).quantize(Decimal("0.01"))


def test_saved_margin_levels_still_recalculate_and_others_are_refused():
    assert calculate_corporativo(CorporateInput(guests=100, margin=0.35), table()).margin_pct == Decimal("0.35")
    with pytest.raises(ValueError):
        calculate_corporativo(CorporateInput(guests=100, margin=0.4), table())


def test_higher_item_price_is_used_without_lock():
    result = calculate_porta([{"code": "q30_cubo_5_faces", "qty": 10}], SAT, SUN, table(q30_cubo_5_faces=25))
    line = result.lines[0]
    assert line["unit_price"] == Decimal("25.00") and line["subtotal"] == Decimal("250.00")
    assert line["price_overridden"] is True and line["catalog_unit_price"] == Decimal("20.00")
    assert not result.locked


def test_lower_item_price_locks_as_discount():
    result = calculate_porta([{"code": "q30_cubo_5_faces", "qty": 10}], SAT, SUN, table(q30_cubo_5_faces=15))
    assert lock_codes(result) == {"desconto"}


def test_price_for_item_without_price_unlocks_it():
    result = calculate_porta([{"code": "ac_talha_5m", "qty": 2}], SAT, SUN, table(ac_talha_5m=80))
    assert result.total == Decimal("160.00") and "item_sem_preco" not in lock_codes(result)


def test_final_total_up_down_and_ceiling():
    config = CalcConfig()
    base = calculate_porta([{"code": "q30_cubo_5_faces", "qty": 10}], SAT, SUN, table())  # 200
    up = apply_final_total(base, 260, config)
    assert up.total == Decimal("260.00") and up.manual_adjustment == Decimal("60.00")
    assert up.calculated_total == Decimal("200.00") and up.final_total_edited and not up.locked

    down = apply_final_total(calculate_porta([{"code": "q30_cubo_5_faces", "qty": 10}], SAT, SUN, table()), 150, config)
    assert down.total == Decimal("150.00") and lock_codes(down) == {"desconto"}

    big = calculate_porta([{"code": "q30_cubo_5_faces", "qty": 200}], SAT, SUN, table(q30_cubo_5_faces=100))  # 20.000
    assert "acima_do_teto" in lock_codes(big)
    assert "acima_do_teto" not in lock_codes(apply_final_total(big, 14000, config))

    with pytest.raises(ValueError):
        apply_final_total(calculate_porta([{"code": "q30_cubo_5_faces", "qty": 1}], SAT, SUN, table()), 0, config)


@pytest.fixture
def lead():
    return Customer(name="Lia", phone="5562900000070", product="estrutura_porta").save()


def _save(client, lead, **extra):
    inputs = {"pickup_date": "2026-11-07", "return_date": "2026-11-08",
              "items": [{"code": "q30_cubo_5_faces", "qty": 10}], **extra}
    return client.post(PROPOSALS, {"customer_id": str(lead.id), "mode": "porta", "inputs": inputs}, format="json")


@pytest.mark.django_db
def test_sdr_lowering_final_value_goes_to_approval(sdr_api, lead):
    resp = _save(sdr_api, lead, final_total=150)
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "aguardando_aprovacao" and resp.data["total"] == 150
    assert resp.data["manual_adjustment"] == -50


@pytest.mark.django_db
def test_sdr_raising_values_saves_without_approval(sdr_api, lead):
    resp = _save(sdr_api, lead, final_total=300, price_overrides={"q30_cubo_5_faces": 22})
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "rascunho" and resp.data["total"] == 300


@pytest.mark.django_db
def test_erica_can_lower_without_approval(api_client, lead):
    preview = api_client.post(f"{PROPOSALS}calculate/", {
        "customer_id": str(lead.id), "mode": "porta",
        "inputs": {"pickup_date": "2026-11-07", "return_date": "2026-11-08",
                   "items": [{"code": "q30_cubo_5_faces", "qty": 10}], "price_overrides": {"q30_cubo_5_faces": 15}},
    }, format="json").data
    assert preview["total"] == 150 and preview["locked"] is False
    assert preview["lines"][0]["price_overridden"] is True
    resp = _save(api_client, lead, final_total=120)
    assert resp.data["status"] == "rascunho" and resp.data["total"] == 120
