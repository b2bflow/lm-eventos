"""Novas etapas do funil, migração e transições explícitas."""
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from crm import domain
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.log_service_model import ServiceLog
from crm.repositories.customer_repository import CustomerRepository
from crm.services.pipeline_service import PermissionDeniedError
from database.client.mongodb_client import MongoDBClient


def make_customer(**fields) -> Customer:
    fields.setdefault("phone", f"5562{Customer.objects.count():09d}")
    return Customer(name=fields.pop("name", "Lead"), **fields).save()


def raw_legacy(stage, **extra):
    """Insere direto na coleção, como os dados antigos de produção."""
    doc = {"name": "Antigo", "phone": f"5562{Customer.objects.count():09d}", "customer_state_now": stage,
           "created_at": datetime(2026, 3, 1), "updated_at": datetime(2026, 3, 1), **extra}
    return Customer._get_collection().insert_one(doc).inserted_id


@pytest.mark.django_db
def test_migrate_lm_stages_maps_old_stages_and_is_idempotent():
    ids = {
        "analysis": raw_legacy("ANALYSIS"),
        "budget_no_proposal": raw_legacy("BUDGET", quoted_amount=5000.0),
        "budget_sent": raw_legacy("BUDGET", proposal_sent_at=datetime(2026, 3, 2)),
        "negotiating": raw_legacy("NEGOTIATING", notes="cliente pediu desconto"),
        "won": raw_legacy("WON", contract_value=12680.0),
        "lost": raw_legacy("LOST"),
    }
    out = StringIO()
    call_command("migrate_lm_stages", stdout=out)

    stage = {k: Customer.objects.get(id=v).customer_state_now for k, v in ids.items()}
    assert stage == {
        "analysis": "NEW_LEAD", "budget_no_proposal": "QUALIFIED", "budget_sent": "PROPOSAL_SENT",
        "negotiating": "PROPOSAL_SENT", "won": "CONTRACT_SIGNED", "lost": "LOST",
    }
    won = Customer.objects.get(id=ids["won"])
    assert won.contract_value == 12680.0 and won.owner == "sdr" and won.flags == []
    assert Customer.objects.get(id=ids["negotiating"]).notes == "cliente pediu desconto"
    assert ServiceLog.objects(action_type="STAGE_CHANGED").count() == 5

    out = StringIO()
    call_command("migrate_lm_stages", stdout=out)
    assert "Nenhum lead em etapa antiga" in out.getvalue()
    assert ServiceLog.objects(action_type="STAGE_CHANGED").count() == 5


@pytest.mark.django_db
def test_dry_run_changes_nothing():
    cid = raw_legacy("ANALYSIS")
    call_command("migrate_lm_stages", "--dry-run", stdout=StringIO())
    assert Customer._get_collection().find_one({"_id": cid})["customer_state_now"] == "ANALYSIS"


@pytest.mark.django_db
def test_legacy_records_are_read_with_new_stage_before_migration():
    cid = raw_legacy("WON")
    data = CustomerRepository(MongoDBClient()).get_by_id(str(cid))
    assert data["customer_state_now"] == "CONTRACT_SIGNED"


@pytest.mark.django_db
def test_new_customer_starts_as_new_lead_and_edits_do_not_infer_stage(admin_user):
    service = CrmContainer.get_customer_service()
    customer = service.register_customer({"name": "Ana", "phone": "5562999990001"})
    assert customer["customer_state_now"] == domain.NEW_LEAD

    # Antes, preencher quoted_amount + notes movia sozinho para NEGOTIATING
    updated = service.update_customer_info(customer["id"], {"quoted_amount": 8000, "notes": "ligar amanhã"}, user=admin_user)
    assert updated["customer_state_now"] == domain.NEW_LEAD


@pytest.mark.django_db
def test_summary_tool_style_repository_update_keeps_stage():
    # A SummaryTool grava os campos do evento direto pelo repositório
    customer = make_customer(customer_state_now=domain.QUALIFIED)
    CustomerRepository(MongoDBClient()).update(id=str(customer.id), attributes={
        "event_title": "Formatura", "guest_count": 300, "notes": "resumo", "next_step": "orçar",
        "last_interaction_at": datetime.utcnow(), "new_service": True, "agent": "response_orchestrator",
    })
    customer.reload()
    assert customer.customer_state_now == domain.QUALIFIED and customer.guest_count == 300


@pytest.mark.django_db
def test_stage_endpoint_validates_transitions_and_logs(api_client):
    customer = make_customer()
    url = f"/api/v1/crm/customers/{customer.id}/stage/"

    # Card anda livre: "Proposta enviada" não exige proposta enviada pela calculadora
    assert api_client.post(url, {"stage": "PROPOSAL_SENT"}, format="json").status_code == 200

    # "Novo lead" não é coluna do quadro
    resp = api_client.post(url, {"stage": "NEW_LEAD"}, format="json")
    assert resp.status_code == 400
    assert api_client.post(url, {"stage": "QUALIFIED"}, format="json").status_code == 200

    resp = api_client.post(url, {"stage": "LOST"}, format="json")
    assert resp.status_code == 400 and "motivo" in resp.data["detail"]

    resp = api_client.post(url, {"stage": "LOST", "lost_reason": "preco"}, format="json")
    assert resp.status_code == 200
    assert resp.data["customer_state_now"] == "LOST" and resp.data["lost_reason"] == "preco"

    logs = list(ServiceLog.objects(customer=customer, action_type="STAGE_CHANGED").order_by("created_at"))
    assert [log.metadata["to"] for log in logs] == ["PROPOSAL_SENT", "QUALIFIED", "LOST"]


@pytest.mark.django_db
def test_patch_with_stage_goes_through_validation(api_client):
    customer = make_customer()
    resp = api_client.patch(f"/api/v1/crm/customers/{customer.id}/", {"customer_state_now": "LOST", "venue": "Clube"}, format="json")
    assert resp.status_code == 400
    customer.reload()
    assert customer.venue is None  # nada salvo pela metade


@pytest.mark.django_db
def test_contract_signed_only_by_admin_or_porta_for_door_rental():
    from users.models.user_model import User
    sdr = User.objects.create_user(username="sdr1", password="x", role="sdr")
    lucia = User.objects.create_user(username="lucia", password="x", role="porta")
    pipeline = CrmContainer.get_pipeline_service()

    porta = make_customer(customer_state_now=domain.PROPOSAL_ACCEPTED, product="estrutura_porta")
    evento = make_customer(customer_state_now=domain.PROPOSAL_ACCEPTED, product="corporativo")

    with pytest.raises(PermissionDeniedError):
        pipeline.change_stage(str(porta.id), domain.CONTRACT_SIGNED, user=sdr)
    assert pipeline.change_stage(str(porta.id), domain.CONTRACT_SIGNED, user=lucia)["customer_state_now"] == domain.CONTRACT_SIGNED
    with pytest.raises(PermissionDeniedError):
        pipeline.change_stage(str(evento.id), domain.CONTRACT_SIGNED, user=lucia)


@pytest.mark.django_db
def test_flags_next_action_note_call_and_timeline(api_client):
    customer = make_customer()
    base = f"/api/v1/crm/customers/{customer.id}"

    resp = api_client.post(f"{base}/flags/", {"add": ["ligacao_pendente", "aguardando_cliente"]}, format="json")
    assert resp.status_code == 200 and set(resp.data["flags"]) == {"ligacao_pendente", "aguardando_cliente"}
    assert api_client.post(f"{base}/flags/", {"add": ["inventada"]}, format="json").status_code == 400

    when = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    resp = api_client.post(f"{base}/next-action/", {"next_step": "Ligar para fechar", "next_action_at": when.isoformat()}, format="json")
    assert resp.status_code == 200 and resp.data["next_step"] == "Ligar para fechar"

    assert api_client.post(f"{base}/notes/", {"text": "Cliente prefere WhatsApp"}, format="json").status_code == 201
    resp = api_client.post(f"{base}/calls/", {"outcome": "atendeu", "notes": "Pediu proposta"}, format="json")
    assert resp.status_code == 201

    customer.reload()
    assert customer.first_contact_at is not None
    assert "ligacao_pendente" not in customer.flags

    timeline = api_client.get(f"{base}/timeline/").data
    types = [item["action_type"] for item in timeline]
    assert {"FLAGS_CHANGED", "NEXT_ACTION_SET", "NOTE_ADDED", "CALL_LOGGED"} <= set(types)


@pytest.mark.django_db
def test_board_groups_by_stage_with_filters_and_db_pagination(api_client):
    entered = datetime.utcnow()
    for i in range(35):
        make_customer(customer_state_now=domain.MEETING_SCHEDULED, product="estrutura_porta" if i % 2 else "corporativo",
                      funnel_entered_at=entered)
    make_customer(customer_state_now=domain.QUALIFIED, product="corporativo", flags=["aguardando_erica"],
                  funnel_entered_at=entered, ai_qualified_at=entered)
    make_customer(customer_state_now=domain.QUALIFIED, human_operator=True, funnel_entered_at=entered)
    raw_legacy("WON", funnel_entered_at=entered)
    make_customer(customer_state_now=domain.QUALIFIED, product="social")  # lead antigo: fora do funil zerado

    board = api_client.get("/api/v1/crm/funnel/").data
    assert board[domain.MEETING_SCHEDULED]["count"] == 35 and len(board[domain.MEETING_SCHEDULED]["results"]) == 30
    assert board[domain.MEETING_SCHEDULED]["has_more"] is True
    assert board[domain.QUALIFIED]["count"] == 1  # operador humano e lead antigo ficam fora
    assert board[domain.CONTRACT_SIGNED]["count"] == 1  # legado aparece na coluna nova

    only_ai = api_client.get("/api/v1/crm/funnel/", {"ai_qualified": "true"}).data
    assert only_ai[domain.QUALIFIED]["count"] == 1 and only_ai[domain.MEETING_SCHEDULED]["count"] == 0

    more = api_client.get("/api/v1/crm/funnel/", {"stage": "MEETING_SCHEDULED", "offset": 30}).data
    assert len(more[domain.MEETING_SCHEDULED]["results"]) == 5

    filtered = api_client.get("/api/v1/crm/funnel/", {"product": "corporativo", "flag": "aguardando_erica"}).data
    assert filtered[domain.QUALIFIED]["count"] == 1 and filtered[domain.MEETING_SCHEDULED]["count"] == 0
    with_human = api_client.get("/api/v1/crm/funnel/", {"include_human": "true"}).data
    assert with_human[domain.QUALIFIED]["count"] == 2


@pytest.mark.django_db
def test_dashboard_still_opens_with_new_stages(api_client):
    make_customer(customer_state_now=domain.CONTRACT_SIGNED, contract_value=10000)
    make_customer(customer_state_now=domain.PROPOSAL_SENT, quoted_amount=5000)
    raw_legacy("ANALYSIS", created_at=datetime.utcnow())
    resp = api_client.get("/api/v1/analytics/dashboard/metrics/")
    assert resp.status_code == 200
    assert resp.data["events_confirmed"] == 1
    assert resp.data["stage_counts"]["NEW_LEAD"] == 1
    assert resp.data["confirmed_revenue"] == 10000
