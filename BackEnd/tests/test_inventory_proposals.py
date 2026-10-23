"""Estoque (carga inicial, disponibilidade, reservas) e ciclo da proposta."""
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.log_service_model import ServiceLog
from crm.models.sdr_task_model import SdrTask
from inventory.models import InventoryItem, InventoryReservation

PORTA_INPUTS = {"pickup_date": "2026-10-23", "return_date": "2026-10-26",
                "items": [{"code": "q30_torre_5m", "qty": 100}, {"code": "q30_cubo_5_faces", "qty": 8}]}


@pytest.fixture
def stock():
    call_command("seed_inventory", stdout=StringIO())


@pytest.fixture
def lead():
    return Customer(name="Lucas", phone="5562988887777", customer_state_now=domain.QUALIFIED,
                    product="estrutura_porta").save()


@pytest.fixture
def sdr_client(db):
    from rest_framework.test import APIClient
    from users.models.user_model import User
    client = APIClient()
    client.force_authenticate(User.objects.create_user(username="sdr", password="x", role="sdr"))
    return client


@pytest.fixture
def contacts():
    cfg = LmSettings.get()
    cfg.approval_phone = "120363000000000000-group"
    cfg.lucia_phone = "5562900000003"
    cfg.save()


# --- Carga inicial ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_inventory_quantities_and_sold_items_removed(stock):
    def qty(code):
        return InventoryItem.objects.get(code=code).qty_total
    assert qty("q30_torre_5m") == 113 and qty("q30_torre_2_5m") == 10 and qty("q30_cubo_5_faces") == 215
    assert qty("q15_torre_3m") == 8 and qty("q15_cubo") == 15
    assert qty("ac_gradil_3m") == 32 and qty("ac_talha_10m") == 8
    assert qty("som_ate_150") is None  # não contado
    names = " ".join(i.name.lower() for i in InventoryItem.objects)
    for sold in ("escada de palco", "gradil 1,60", "gradil 2,20", "mão francesa", "pé de", "pirulito", "tábua", "travessa"):
        assert sold not in names
    assert all(i.approximate_count for i in InventoryItem.objects)


@pytest.mark.django_db
def test_seed_inventory_is_idempotent_and_keeps_manual_counts(stock):
    total = InventoryItem.objects.count()
    item = InventoryItem.objects.get(code="q30_torre_5m")
    item.qty_total = 110
    item.save()
    call_command("seed_inventory", stdout=StringIO())
    assert InventoryItem.objects.count() == total
    assert InventoryItem.objects.get(code="q30_torre_5m").qty_total == 110
    call_command("seed_inventory", "--reset-counts", stdout=StringIO())
    assert InventoryItem.objects.get(code="q30_torre_5m").qty_total == 113


@pytest.mark.django_db
def test_items_endpoint_shows_total_reserved_and_available_by_date(api_client, stock, lead):
    item = InventoryItem.objects.get(code="q30_torre_5m")
    InventoryReservation(item=item, proposal_id="p1", customer=lead, qty=40,
                         start=datetime(2026, 10, 23), end=datetime(2026, 10, 27)).save()

    during = {i["code"]: i for i in api_client.get("/api/v1/inventory/items/", {"line": "Q30", "start": "2026-10-24", "end": "2026-10-25"}).data}
    assert during["q30_torre_5m"]["qty_total"] == 113
    assert during["q30_torre_5m"]["reserved"] == 40 and during["q30_torre_5m"]["available"] == 73
    assert during["q30_torre_5m"]["sale_price"] == 75.0

    after = {i["code"]: i for i in api_client.get("/api/v1/inventory/items/", {"start": "2026-10-28", "end": "2026-10-29"}).data}
    assert after["q30_torre_5m"]["available"] == 113
    assert after["som_ate_150"]["available"] is None


# --- Proposta --------------------------------------------------------------------------------

@pytest.mark.django_db
def test_sent_and_accepted_value_reaches_card_and_quote(sdr_client, stock, lead, contacts, zapi_outbox):
    from crm.models.quote_model import Quote
    quote = Quote(customer=lead, status="BUDGET", quoted_amount=999).save()
    first = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta",
                                                         "inputs": PORTA_INPUTS}, format="json").data
    second = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": {
        **PORTA_INPUTS, "items": [{"code": "q30_torre_5m", "qty": 10}]}}, format="json").data
    sdr_client.post(f"/api/v1/sales/proposals/{first['id']}/send/")
    sdr_client.post(f"/api/v1/sales/proposals/{second['id']}/send/")
    lead.reload()
    quote.reload()
    assert lead.quoted_amount == second["total"] == 750.0 and quote.quoted_amount == 750.0 and quote.proposal_sent_at
    # O cliente aceitou a primeira versão: card, painéis e cotação passam a mostrar o valor dela
    assert sdr_client.post(f"/api/v1/sales/proposals/{first['id']}/accept/").status_code == 200
    lead.reload()
    quote.reload()
    assert lead.quoted_amount == first["total"] == 7660.0 and quote.quoted_amount == 7660.0


@pytest.mark.django_db
def test_full_porta_cycle_send_accept_reserves_stock(sdr_client, stock, lead, contacts, zapi_outbox):
    resp = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": PORTA_INPUTS}, format="json")
    assert resp.status_code == 201, resp.data
    proposal = resp.data
    assert proposal["status"] == "rascunho" and proposal["total"] == 7660.0  # 100x75 + 8x20
    assert proposal["version"] == 1

    sent = sdr_client.post(f"/api/v1/sales/proposals/{proposal['id']}/send/").data
    assert sent["status"] == "enviada" and sent["valid_until"]
    lead.reload()
    assert lead.customer_state_now == domain.PROPOSAL_SENT and lead.quoted_amount == 7660.0 and lead.proposal_sent_at
    assert SdrTask.objects(customer=lead, type="proposta_vencendo").count() == 1
    assert ServiceLog.objects(customer=lead, action_type="PROPOSAL_SENT").count() == 1

    accepted = sdr_client.post(f"/api/v1/sales/proposals/{proposal['id']}/accept/").data
    assert accepted["status"] == "aceita"
    lead.reload()
    assert lead.customer_state_now == domain.PROPOSAL_ACCEPTED and lead.owner == "lucia"
    assert InventoryReservation.objects(proposal_id=proposal["id"], status="reservado").count() == 2
    assert any(m.get("phone") == "5562900000003" and "Locação de porta fechada" in m["message"] for m in zapi_outbox)

    # Outra proposta no mesmo fim de semana passa do disponível: alerta vermelho e trava
    other = Customer(name="Outro", phone="5562977776666", product="estrutura_porta").save()
    preview = sdr_client.post("/api/v1/sales/proposals/calculate/", {"mode": "porta", "inputs": {
        **PORTA_INPUTS, "items": [{"code": "q30_torre_5m", "qty": 20}]}, "customer_id": str(other.id)}, format="json").data
    line = preview["lines"][0]
    assert line["available"] == 13 and line["shortage"] is True
    assert any(r["code"] == "estoque_insuficiente" for r in preview["lock_reasons"])


@pytest.mark.django_db
def test_locked_proposal_requires_erica_approval(sdr_client, api_client, stock, lead, contacts, zapi_outbox):
    inputs = {**PORTA_INPUTS, "pickup_date": "2026-10-16", "return_date": "2026-10-26"}  # 10 dias
    proposal = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": inputs}, format="json").data
    assert proposal["status"] == "aguardando_aprovacao"
    assert any(r["code"] == "locacao_acima_1_semana" for r in proposal["lock_reasons"])
    lead.reload()
    assert "aguardando_aprovacao_desconto" in lead.flags
    approval_msg = [m for m in zapi_outbox if m.get("phone") == "120363000000000000-group"]
    assert approval_msg and "R$ 15.320,00" in approval_msg[0]["message"] and "/funil?lead=" in approval_msg[0]["message"]

    assert sdr_client.post(f"/api/v1/sales/proposals/{proposal['id']}/send/").status_code == 400
    assert sdr_client.post(f"/api/v1/sales/proposals/{proposal['id']}/approve/", {"approve": True}, format="json").status_code == 403

    pending = api_client.get("/api/v1/sales/proposals/", {"status": "aguardando_aprovacao"}).data
    assert [p["id"] for p in pending] == [proposal["id"]]
    decided = api_client.post(f"/api/v1/sales/proposals/{proposal['id']}/approve/", {"approve": True, "note": "Ok, cliente antigo"}, format="json").data
    assert decided["status"] == "aprovada"
    lead.reload()
    assert "aguardando_aprovacao_desconto" not in lead.flags
    assert sdr_client.post(f"/api/v1/sales/proposals/{proposal['id']}/send/").status_code == 200


@pytest.mark.django_db
def test_manual_adjustment_only_admin(sdr_client, api_client, lead):
    inputs = {"guests": 100, "event_date": "2026-11-20", "margin": 0.35, "with_invoice": True, "manual_adjustment": 100}
    body = {"customer_id": str(lead.id), "mode": "corporativo", "inputs": inputs}
    assert sdr_client.post("/api/v1/sales/proposals/", body, format="json").status_code == 403
    resp = api_client.post("/api/v1/sales/proposals/", body, format="json")
    assert resp.status_code == 201 and resp.data["manual_adjustment"] == 100.0


@pytest.mark.django_db
def test_editing_creates_new_version_and_supersedes_old(sdr_client, stock, lead):
    first = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": PORTA_INPUTS}, format="json").data
    second = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": {
        **PORTA_INPUTS, "items": [{"code": "q30_torre_4m", "qty": 10}]}, "replaces": first["id"]}, format="json").data
    assert second["version"] == 2 and second["total"] == 600.0
    history = sdr_client.get("/api/v1/sales/proposals/", {"customer": str(lead.id)}).data
    assert [(p["version"], p["status"]) for p in history] == [(2, "rascunho"), (1, "substituida")]


@pytest.mark.django_db
def test_corporate_needs_event_date(sdr_client, lead):
    resp = sdr_client.post("/api/v1/sales/proposals/calculate/", {"mode": "corporativo", "inputs": {"guests": 100}}, format="json")
    assert resp.status_code == 400 and "data do evento" in resp.data["detail"]
    lead.event_date = datetime(2026, 11, 20)
    lead.save()
    resp = sdr_client.post("/api/v1/sales/proposals/calculate/", {"mode": "corporativo", "customer_id": str(lead.id),
                                                                  "inputs": {"guests": 100, "margin": 0.2, "with_invoice": False}}, format="json")
    assert resp.status_code == 200 and resp.data["total"] == 1560.0
    assert sdr_client.post("/api/v1/sales/proposals/calculate/", {"mode": "festa", "inputs": {}}, format="json").status_code == 400


@pytest.mark.django_db
def test_social_with_competitor_quote_becomes_meeting_with_erica(sdr_client, stock, lead, contacts, zapi_outbox):
    inputs = {"event_date": "2026-11-21", "guests": 120, "structure": "gol_3x4", "led_m2": 6, "dj": True,
              "competitor_quote": True, "margin": 0.2, "with_invoice": False}
    resp = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "social", "inputs": inputs}, format="json")
    assert resp.status_code == 201, resp.data
    proposal = resp.data
    assert proposal["mode"] == "social" and proposal["status"] == "aguardando_aprovacao"
    assert proposal["requires_meeting"] is True
    lead.reload()
    assert {"aguardando_aprovacao_desconto", "aguardando_erica"} <= set(lead.flags)
    msg = [m for m in zapi_outbox if m.get("phone") == "120363000000000000-group"][0]["message"]
    assert "reunião com a Erica" in msg and "orçamento concorrente" in msg


@pytest.mark.django_db
def test_single_product_checks_stock_on_the_date(sdr_client, stock, lead):
    body = {"mode": "produto_unico", "customer_id": str(lead.id), "inputs": {
        "event_date": "2026-11-21", "items": [{"code": "palco_passa_cabo", "qty": 8}], "delivery": "entrega"}}
    preview = sdr_client.post("/api/v1/sales/proposals/calculate/", body, format="json").data
    assert preview["lines"][0]["available"] == 5 and preview["lines"][0]["shortage"] is True
    assert preview["total"] == 240.0 + 850.0  # 8 x 30 + frete, carga e descarga
    resp = sdr_client.post("/api/v1/sales/proposals/", {**body, "inputs": {**body["inputs"], "items": [
        {"code": "palco_passa_cabo", "qty": 2}], "delivery": "retirada"}}, format="json")
    assert resp.status_code == 201 and resp.data["status"] == "rascunho" and resp.data["total"] == 60.0


@pytest.mark.django_db
def test_sent_proposal_expires_after_validity(sdr_client, stock, lead):
    from sales.services.proposal_service import ProposalService
    proposal = sdr_client.post("/api/v1/sales/proposals/", {"customer_id": str(lead.id), "mode": "porta", "inputs": PORTA_INPUTS}, format="json").data
    service = ProposalService()
    service.send(proposal["id"], now=datetime.utcnow() - timedelta(days=6))
    assert service.expire() == 1
    assert sdr_client.get(f"/api/v1/sales/proposals/{proposal['id']}/").data["status"] == "vencida"


@pytest.mark.django_db
def test_movements_update_reservation_status(api_client, stock, lead):
    item = InventoryItem.objects.get(code="q30_torre_5m")
    InventoryReservation(item=item, proposal_id="p9", customer=lead, qty=10,
                         start=datetime(2026, 10, 23), end=datetime(2026, 10, 27)).save()
    body = {"code": "q30_torre_5m", "qty": 10, "type": "saida", "customer_id": str(lead.id), "proposal_id": "p9"}
    assert api_client.post("/api/v1/inventory/movements/", body, format="json").status_code == 201
    assert InventoryReservation.objects.get(proposal_id="p9").status == "retirado"
    api_client.post("/api/v1/inventory/movements/", {**body, "type": "retorno"}, format="json")
    assert InventoryReservation.objects.get(proposal_id="p9").status == "devolvido"


@pytest.mark.django_db
def test_sdr_cannot_edit_inventory(sdr_client, stock):
    item = InventoryItem.objects.get(code="q30_torre_5m")
    assert sdr_client.patch(f"/api/v1/inventory/items/{item.id}/", {"qty_total": 1}, format="json").status_code == 403


def test_format_brl():
    from sales.formatting import format_brl
    assert format_brl(12680) == "R$ 12.680,00"
    assert format_brl(1234567.891) == "R$ 1.234.567,89"
    assert format_brl(45) == "R$ 45,00"
