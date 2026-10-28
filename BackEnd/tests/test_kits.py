"""Kits do estoque ("Novo kit"): preço do kit, peças no estoque, na reserva e no PDF."""
from io import StringIO

import pytest
from django.core.management import call_command

from inventory.models import InventoryItem, InventoryKit, InventoryReservation

KITS = "/api/v1/inventory/kits/"
CALC = "/api/v1/sales/proposals/calculate/"


@pytest.fixture
def stock():
    call_command("seed_inventory", stdout=StringIO())
    InventoryItem.objects(code="som_caixa_ativa").update(set__qty_total=10)
    InventoryItem.objects(code="som_mic_sem_fio").update(set__qty_total=6)
    InventoryItem.objects(code="som_pedestal").update(set__qty_total=4)


def _new_kit(client, **extra):
    body = {"name": "Som para 80 pessoas", "line": "Som", "pieces": [
        {"code": "som_caixa_ativa", "qty": 2}, {"code": "som_mic_sem_fio", "qty": 1}], **extra}
    return client.post(KITS, body, format="json")


@pytest.mark.django_db
def test_builtin_sound_kits_are_listed_and_editable_not_removable(api_client, stock):
    kits = {k["code"]: k for k in api_client.get(KITS).data}
    assert kits["som_ate_150"]["builtin"] and kits["som_ate_150"]["sale_price"] == 1300
    assert [(p["code"], p["qty"]) for p in kits["som_ate_150"]["pieces"]] == [("som_caixa_ativa", 4), ("som_mic_sem_fio", 1)]
    # 10 caixas / 4 por kit = 2; 6 microfones = 6: a caixa limita
    assert kits["som_ate_150"]["buildable"] == 2 and kits["som_ate_150"]["limiting_piece"] == "Caixa de som ativa"
    kit_id = kits["som_ate_150"]["id"]
    resp = api_client.patch(f"{KITS}{kit_id}/", {"pieces": [{"code": "som_caixa_ativa", "qty": 2}], "name": "X"},
                            format="json")
    assert resp.status_code == 200 and resp.data["name"] == "Som até 150 pessoas" and resp.data["buildable"] == 5
    assert api_client.delete(f"{KITS}{kit_id}/").status_code == 400
    # A calculadora passa a usar a nova composição
    preview = api_client.post(CALC, {"mode": "corporativo", "inputs": {"guests": 100, "event_date": "2026-11-20"}},
                              format="json").data
    line = next(l for l in preview["lines"] if l["code"] == "som_ate_150")
    assert [(c["code"], c["qty"]) for c in line["components"]] == [("som_caixa_ativa", 2)]


@pytest.mark.django_db
def test_create_kit_validates_and_only_admin_sets_price(api_client, porta_api, sdr_api, stock):
    assert _new_kit(sdr_api).status_code == 403
    assert _new_kit(porta_api, sale_price=900).status_code == 403
    created = _new_kit(porta_api)
    assert created.status_code == 201 and created.data["code"] == "kit_som_para_80_pessoas"
    assert created.data["sale_price"] is None and created.data["buildable"] == 5
    assert _new_kit(porta_api).status_code == 400  # nome repetido
    bad = [
        {"name": "Vazio", "line": "Som", "pieces": []},
        {"name": "Sem item", "line": "Som", "pieces": [{"code": "nao_existe", "qty": 1}]},
        {"name": "Kit de kit", "line": "Som", "pieces": [{"code": "som_ate_150", "qty": 1}]},
        {"name": "Meia caixa", "line": "Som", "pieces": [{"code": "som_caixa_ativa", "qty": 0.5}]},
        {"name": "Linha", "line": "Cozinha", "pieces": [{"code": "som_caixa_ativa", "qty": 1}]},
    ]
    for body in bad:
        assert porta_api.post(KITS, body, format="json").status_code == 400, body
    priced = api_client.patch(f"{KITS}{created.data['id']}/", {"sale_price": "850,50"}, format="json")
    assert priced.status_code == 200 and priced.data["sale_price"] == 850.5


@pytest.mark.django_db
def test_kit_is_sold_by_kit_but_stock_and_pdf_use_pieces(api_client, stock):
    kit = _new_kit(api_client, sale_price=700).data
    inputs = {"event_date": "2026-11-20", "items": [{"code": kit["code"], "qty": 2}]}
    preview = api_client.post(CALC, {"mode": "produto_unico", "inputs": inputs}, format="json").data
    line = next(l for l in preview["lines"] if l["code"] == kit["code"])
    assert line["subtotal"] == 1400 and line["qty"] == 2 and not line["shortage"]
    # 6 kits pedem 12 caixas: só há 10
    inputs["items"][0]["qty"] = 6
    preview = api_client.post(CALC, {"mode": "produto_unico", "inputs": inputs}, format="json").data
    assert any("Caixa de som ativa: pedido 12, disponível 10" in (r["detail"] or "") for r in preview["lock_reasons"]), preview["lock_reasons"]

    from sales.services.proposal_pdf import build_pdf_context
    proposal = {"mode": "produto_unico", "inputs": {}, "lines": preview["lines"], "costs": [], "total": 1}
    settings = {"proposal_validity_days": 5, "payment_terms_text": "", "down_payment_text": "", "cancellation_text": ""}
    text = " | ".join(i for b in build_pdf_context(proposal, {"name": "Ana"}, settings)["blocks"] for i in b["items"])
    assert "12 Caixa de som ativa" in text and "06 Microfone sem fio" in text and "Som para 80" not in text

    # Marcado para sair pelo nome, o PDF mostra o kit
    api_client.patch(f"{KITS}{kit['id']}/", {"show_pieces": False}, format="json")
    inputs["items"][0]["qty"] = 1
    preview = api_client.post(CALC, {"mode": "produto_unico", "inputs": inputs}, format="json").data
    proposal["lines"] = preview["lines"]
    text = " | ".join(i for b in build_pdf_context(proposal, {"name": "Ana"}, settings)["blocks"] for i in b["items"])
    assert "01 Som para 80 pessoas" in text and "Caixa" not in text


@pytest.mark.django_db
def test_kit_in_catalog_and_removed_kit_leaves_calculator(api_client, stock):
    kit = _new_kit(api_client, sale_price=700).data
    catalog = api_client.get("/api/v1/sales/catalog/").data
    assert any(i["code"] == kit["code"] and i.get("is_kit") for i in catalog["items"])
    assert catalog["sound_sets"][kit["code"]] == [{"code": "som_caixa_ativa", "qty": 2.0}, {"code": "som_mic_sem_fio", "qty": 1.0}]
    assert api_client.delete(f"{KITS}{kit['id']}/").status_code == 204
    catalog = api_client.get("/api/v1/sales/catalog/").data
    assert not any(i["code"] == kit["code"] for i in catalog["items"])
    assert kit["code"] not in {k["code"] for k in api_client.get(KITS).data}
    assert kit["code"] in {k["code"] for k in api_client.get(KITS, {"include_inactive": "1"}).data}
    assert api_client.patch(f"{KITS}{kit['id']}/", {"active": True}, format="json").data["active"] is True


@pytest.mark.django_db
def test_reserving_a_kit_reserves_every_piece_and_cancels_together(api_client, stock):
    kit = _new_kit(api_client).data
    period = {"start": "2026-11-20", "end": "2026-11-21", "client_name": "Casamento Ana"}
    too_many = api_client.post(f"{KITS}{kit['id']}/reserve/", {**period, "qty": 6}, format="json")
    assert too_many.status_code == 400 and "Caixa de som ativa: precisa 12, disponível 10" in too_many.data["detail"]
    assert not InventoryReservation.objects.count()
    created = api_client.post(f"{KITS}{kit['id']}/reserve/", {**period, "qty": 3}, format="json")
    assert created.status_code == 201
    assert sorted((r.item.code, r.qty) for r in InventoryReservation.objects) == [("som_caixa_ativa", 6), ("som_mic_sem_fio", 3)]
    detail = api_client.get(f"{KITS}{kit['id']}/", period).data
    assert detail["buildable"] == 2 and [r["kits"] for r in detail["reservations"]] == [3]
    api_client.delete(f"/api/v1/inventory/reservations/{created.data[0]['id']}/")
    assert set(InventoryReservation.objects.distinct("status")) == {"cancelado"}


@pytest.mark.django_db
def test_piece_of_a_kit_cannot_leave_stock_and_shows_its_kits(api_client, stock):
    kit = _new_kit(api_client).data
    mic = InventoryItem.objects.get(code="som_mic_sem_fio")
    detail = api_client.get(f"/api/v1/inventory/items/{mic.id}/").data
    assert {k["name"] for k in detail["kits"]} >= {"Som para 80 pessoas", "Som até 150 pessoas"}
    resp = api_client.delete(f"/api/v1/inventory/items/{mic.id}/")
    assert resp.status_code == 400 and "Tire do kit" in resp.data["detail"]
    assert api_client.patch(f"/api/v1/inventory/items/{mic.id}/", {"active": False}, format="json").status_code == 400
    assert InventoryKit.objects.get(code=kit["code"]).active
