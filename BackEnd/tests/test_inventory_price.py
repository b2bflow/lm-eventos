"""Preço de venda editado na tela de Estoque (inclusive itens criados por ela)."""
import pytest

from inventory.models import InventoryItem
from sales.services.pricing_service import effective_price_table
from sales.services.quote_calculator import unit_price

ITEMS = "/api/v1/inventory/items/"
CALC = "/api/v1/sales/proposals/calculate/"
PORTA_DATES = {"pickup_date": "2026-11-07", "return_date": "2026-11-08"}


def _row(client, code):
    return next(r for r in client.get(ITEMS).data if r["code"] == code)


@pytest.mark.django_db
def test_admin_sets_price_for_item_without_price(api_client):
    talha = InventoryItem(code="ac_talha_5m", line="Acessórios", name="Talha 5 m", qty_total=6).save()
    assert _row(api_client, "ac_talha_5m")["sale_price"] is None

    resp = api_client.patch(f"{ITEMS}{talha.id}/", {"sale_price": "80,50"}, format="json")
    assert resp.status_code == 200, resp.data
    assert _row(api_client, "ac_talha_5m")["sale_price"] == 80.5
    assert api_client.get(f"{ITEMS}{talha.id}/").data["sale_price"] == 80.5
    catalog = {i["code"]: i for i in api_client.get("/api/v1/sales/catalog/").data["items"]}
    assert catalog["ac_talha_5m"]["sale_price"] == 80.5

    result = api_client.post(CALC, {"mode": "porta", "inputs": {**PORTA_DATES, "items": [{"code": "ac_talha_5m", "qty": 2}]}},
                             format="json").data
    assert result["total"] == 161 and not result["locked"]

    # null volta ao padrão do catálogo (sem preço)
    api_client.patch(f"{ITEMS}{talha.id}/", {"sale_price": None}, format="json")
    assert _row(api_client, "ac_talha_5m")["sale_price"] is None


@pytest.mark.django_db
def test_tower_price_per_piece_replaces_metro_calculation(api_client):
    torre = InventoryItem(code="q30_torre_3m", line="Q30", name="Torre Q30 3 m", billing_unit="metro", qty_total=127).save()
    assert unit_price("q30_torre_3m", effective_price_table()) == 45  # 3 m x R$ 15
    api_client.patch(f"{ITEMS}{torre.id}/", {"sale_price": 50}, format="json")
    assert unit_price("q30_torre_3m", effective_price_table()) == 50


@pytest.mark.django_db
def test_item_created_on_stock_page_gets_price_and_enters_calculator(api_client):
    resp = api_client.post(ITEMS, {"name": "Cubo 60", "line": "Q30", "qty_total": 4, "sale_price": 35}, format="json")
    assert resp.status_code == 201, resp.data
    code = resp.data["code"]
    catalog = {i["code"]: i for i in api_client.get("/api/v1/sales/catalog/").data["items"]}
    assert catalog[code]["sale_price"] == 35 and catalog[code]["line"] == "Q30"

    result = api_client.post(CALC, {"mode": "porta", "inputs": {**PORTA_DATES, "items": [{"code": code, "qty": 2}]}},
                             format="json").data
    assert result["total"] == 70 and result["lines"][0]["block"] == "estrutura"


@pytest.mark.django_db
def test_only_admin_sets_prices(porta_api):
    item = InventoryItem(code="ac_gradil_3m", line="Acessórios", name="Gradil 3 m", qty_total=32).save()
    assert porta_api.patch(f"{ITEMS}{item.id}/", {"sale_price": 10}, format="json").status_code == 403
    assert porta_api.patch(f"{ITEMS}{item.id}/", {"qty_total": 30}, format="json").status_code == 200
    assert porta_api.post(ITEMS, {"name": "Novo", "line": "Acessórios", "sale_price": 5}, format="json").status_code == 403


@pytest.mark.django_db
def test_invalid_price_is_refused_without_partial_changes(api_client):
    item = InventoryItem(code="ac_cinta_branca", line="Acessórios", name="Cinta branca", qty_total=28).save()
    resp = api_client.patch(f"{ITEMS}{item.id}/", {"sale_price": -1, "name": "Outro nome"}, format="json")
    assert resp.status_code == 400
    item.reload()
    assert item.name == "Cinta branca"
