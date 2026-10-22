"""Aba "Valores" em Configurações: preço do metro, custos operacionais e faixas de som."""
import pytest

from sales.services.pricing_service import effective_price_table
from sales.services.quote_calculator import unit_price

PRICES = "/api/v1/sales/prices/"


def _by(rows, key, value):
    return next(r for r in rows if r[key] == value)


@pytest.mark.django_db
def test_lists_defaults(api_client):
    data = api_client.get(PRICES).data
    assert _by(data["metro_price"], "line", "Q30")["price"] == 15
    assert _by(data["operational_costs"], "code", "carga")["price"] == 300
    tier = _by(data["sound_tiers"], "code", "som_ate_150")
    assert tier["limit"] == 150 and tier["price"] == 1300 and tier["default"] == 1300


@pytest.mark.django_db
def test_admin_edits_values_and_calculator_uses_them(api_client):
    resp = api_client.patch(PRICES, {
        "metro_price": {"Q30": "16,50"},
        "operational_costs": {"carga": 350},
        "sound_tiers": {"som_ate_150": 1400},
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert _by(resp.data["metro_price"], "line", "Q30")["price"] == 16.5

    table = effective_price_table()
    assert unit_price("q30_torre_3m", table) == 49.5  # 3 m x R$ 16,50
    assert table["operational_costs"]["carga"] == 350
    assert unit_price("som_ate_150", table) == 1400
    catalog = api_client.get("/api/v1/sales/catalog/").data
    assert _by(catalog["operational_costs"], "code", "carga")["price"] == 350

    # vazio volta ao padrão
    api_client.patch(PRICES, {"metro_price": {"Q30": ""}, "sound_tiers": {"som_ate_150": None}}, format="json")
    table = effective_price_table()
    assert unit_price("q30_torre_3m", table) == 45 and unit_price("som_ate_150", table) == 1300
    assert table["operational_costs"]["carga"] == 350


@pytest.mark.django_db
def test_rejects_invalid_values_without_saving(api_client):
    resp = api_client.patch(PRICES, {"operational_costs": {"carga": 10, "frete": -5}}, format="json")
    assert resp.status_code == 400
    assert effective_price_table()["operational_costs"]["carga"] == 300
    assert api_client.patch(PRICES, {"operational_costs": {"inventado": 10}}, format="json").status_code == 400


@pytest.mark.django_db
def test_only_admin_edits(sdr_api, porta_api):
    assert sdr_api.get(PRICES).status_code == 200
    for client in (sdr_api, porta_api):
        assert client.patch(PRICES, {"operational_costs": {"carga": 1}}, format="json").status_code == 403
    assert effective_price_table()["operational_costs"]["carga"] == 300
