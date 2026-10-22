"""Serviços de qualificação (seção 4.1) chamados pela API, sem IA, e regras da fila da SDR."""
from datetime import datetime, timedelta

import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.container import CrmContainer
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import DEFAULT_BUSINESS_HOURS, LmSettings
from crm.models.sdr_task_model import SdrTask
from crm.services.business_hours import first_call_due

# 16/10/2026 é sexta-feira. Horários em UTC (Brasília = UTC-3).
FRIDAY_10H_BRT = datetime(2026, 10, 16, 13, 0)
FRIDAY_20H_BRT = datetime(2026, 10, 16, 23, 0)
SATURDAY_13H_BRT = datetime(2026, 10, 17, 16, 0)


@pytest.fixture
def lead():
    customer = Customer(name="Marcos", phone="5562999991111").save()
    ConversationModel(customer=customer, tag="AGENTE", ai_active=True).save()
    return customer


@pytest.fixture
def settings_with_contacts():
    cfg = LmSettings.get()
    cfg.sdr_phone = "5562900000001"
    cfg.erica_phone = "5562900000002"
    cfg.save()
    return cfg


def base(customer):
    return f"/api/v1/crm/customers/{customer.id}"


@pytest.mark.django_db
def test_acceptance_porta_lead_flows_to_qualified_with_attachment_pending_and_call_task(
        api_client, lead, settings_with_contacts, zapi_outbox):
    url = base(lead)
    assert api_client.post(f"{url}/qualification/start/", {"product": "estrutura_porta"}, format="json").status_code == 200
    assert api_client.post(f"{url}/qualification/field/", {"field": "data_retirada", "value": "24/10/2026"}, format="json").status_code == 200
    assert api_client.post(f"{url}/qualification/field/", {"field": "data_devolucao", "value": "27/10/2026"}, format="json").status_code == 200
    assert api_client.post(f"{url}/qualification/field/", {"field": "data_evento", "value": "25/10/2026"}, format="json").status_code == 200
    assert api_client.post(f"{url}/qualification/field/", {"field": "lista_pecas", "value": "não sei"}, format="json").status_code == 200
    resp = api_client.post(f"{url}/qualification/attachment/",
                           {"url": "https://cdn.z-api.io/foto-estrutura.jpg", "kind": "lista_pecas", "name": "foto.jpg"}, format="json")
    assert resp.status_code == 200
    resp = api_client.post(f"{url}/qualification/qualify/", {"pending_fields": ["forma_retirada"]}, format="json")
    assert resp.status_code == 200, resp.data

    data = resp.data
    assert data["customer_state_now"] == "QUALIFIED"
    assert data["qualified_at"]
    assert data["attachments"][0]["url"].endswith("foto-estrutura.jpg")
    assert set(data["pending_fields"]) == {"lista_pecas", "forma_retirada"}
    assert data["qualification"]["data_retirada"] == "24/10/2026"
    assert data["event_date"].startswith("2026-10-25")
    assert "ligacao_pendente" in data["flags"]

    task = SdrTask.objects.get(customer=lead.id)
    assert task.type == "ligar_15min" and task.status == "pending"

    board = api_client.get("/api/v1/crm/funnel/").data
    card = board["QUALIFIED"]["results"][0]
    assert card["id"] == str(lead.id) and card["attachments"]

    sdr_msg = [m for m in zapi_outbox if m.get("phone") == "5562900000001"]
    assert sdr_msg and "Novo lead qualificado" in sdr_msg[0]["message"]
    assert all(ord(ch) < 0x1F000 for ch in sdr_msg[0]["message"])  # sem emoji


@pytest.mark.django_db
def test_acceptance_partial_lead_shows_in_new_lead_with_saved_data(api_client, lead):
    url = base(lead)
    api_client.post(f"{url}/qualification/start/", {"product": "corporativo"}, format="json")
    api_client.post(f"{url}/qualification/field/", {"field": "publico", "value": "300 pessoas"}, format="json")
    api_client.post(f"{url}/qualification/field/", {"field": "empresa", "value": "Acme Ltda"}, format="json")

    board = api_client.get("/api/v1/crm/funnel/").data
    card = board["NEW_LEAD"]["results"][0]
    assert card["guest_count"] == 300 and card["company"] == "Acme Ltda"
    assert card["qualification"] == {"publico": "300 pessoas", "empresa": "Acme Ltda"}
    assert board["QUALIFIED"]["count"] == 0


@pytest.mark.django_db
def test_save_field_rejects_field_from_other_product(api_client, lead):
    url = base(lead)
    api_client.post(f"{url}/qualification/start/", {"product": "produto_unico"}, format="json")
    resp = api_client.post(f"{url}/qualification/field/", {"field": "led_m2", "value": 12}, format="json")
    assert resp.status_code == 400
    assert api_client.post(f"{url}/qualification/start/", {"product": "inexistente"}, format="json").status_code == 400


@pytest.mark.django_db
def test_real_value_clears_pending(api_client, lead):
    url = base(lead)
    api_client.post(f"{url}/qualification/start/", {"product": "social"}, format="json")
    api_client.post(f"{url}/qualification/field/", {"field": "dj", "value": "Não sei"}, format="json")
    assert Customer.objects.get(id=lead.id).pending_fields == ["dj"]
    api_client.post(f"{url}/qualification/field/", {"field": "dj", "value": "sim"}, format="json")
    assert Customer.objects.get(id=lead.id).pending_fields == []


@pytest.mark.django_db
def test_acceptance_human_operator_pauses_ai_notifies_erica_and_skips_sdr_queue(
        api_client, lead, settings_with_contacts, zapi_outbox):
    url = base(lead)
    resp = api_client.post(f"{url}/human-operator/", {"reason": "Parceiro antigo (cerimonialista)"}, format="json")
    assert resp.status_code == 200
    assert resp.data["human_operator"] is True and resp.data["owner"] == "erica"

    conv = ConversationModel.objects.get(customer=lead.id)
    assert conv.tag == "OPERADOR" and conv.ai_active is False and conv.needs_attention is True

    erica_msg = [m for m in zapi_outbox if m.get("phone") == "5562900000002"]
    assert erica_msg and "Parceiro antigo" in erica_msg[0]["message"] and "(62) 99999-1111" in erica_msg[0]["message"]

    # Mesmo qualificado depois, não entra na fila da SDR nem aparece no funil padrão
    api_client.post(f"{url}/qualification/qualify/", {}, format="json")
    assert SdrTask.objects(customer=lead.id).count() == 0
    assert api_client.get("/api/v1/crm/funnel/").data["QUALIFIED"]["count"] == 0
    assert api_client.get("/api/v1/crm/tasks/").data == []


@pytest.mark.django_db
def test_call_answered_completes_call_task(api_client, lead):
    url = base(lead)
    api_client.post(f"{url}/qualification/qualify/", {}, format="json")
    api_client.post(f"{url}/calls/", {"outcome": "atendeu"}, format="json")
    assert SdrTask.objects.get(customer=lead.id).status == "done"


def test_first_call_due_respects_business_hours():
    hours = DEFAULT_BUSINESS_HOURS
    assert first_call_due(hours, FRIDAY_10H_BRT, 15) == FRIDAY_10H_BRT + timedelta(minutes=15)
    # Sexta 20h -> sábado 9h (sábado abre 8h-12h) = 12:00 UTC
    assert first_call_due(hours, FRIDAY_20H_BRT, 15) == datetime(2026, 10, 17, 12, 0)
    # Sábado 13h (fechado) -> domingo fechado -> segunda 9h = 12:00 UTC
    assert first_call_due(hours, SATURDAY_13H_BRT, 15) == datetime(2026, 10, 19, 12, 0)
    # Segunda 7h (antes de abrir) -> mesma segunda 9h
    assert first_call_due(hours, datetime(2026, 10, 19, 10, 0), 15) == datetime(2026, 10, 19, 12, 0)


@pytest.mark.django_db
def test_qualify_outside_business_hours_schedules_next_day(lead):
    service = CrmContainer.get_lead_qualification_service()
    service.qualify_lead(str(lead.id), now=FRIDAY_20H_BRT)
    assert SdrTask.objects.get(customer=lead.id).due_at == datetime(2026, 10, 17, 12, 0)


@pytest.mark.django_db
def test_stale_new_lead_gets_retomar_task_once():
    now = datetime(2026, 10, 16, 15, 0)
    stale = Customer(name="Parado", phone="5562911110000", created_at=now - timedelta(hours=30),
                     funnel_entered_at=now - timedelta(hours=30)).save()
    conv = ConversationModel(customer=stale).save()
    MessageModel(conversation=conv, customer=stale, role="user", direction="INCOMING", content="oi",
                 created_at=now - timedelta(hours=26)).save()
    recent = Customer(name="Ativo", phone="5562911110001", created_at=now - timedelta(hours=30),
                      funnel_entered_at=now - timedelta(hours=30)).save()
    conv2 = ConversationModel(customer=recent).save()
    MessageModel(conversation=conv2, customer=recent, role="user", direction="INCOMING", content="oi",
                 created_at=now - timedelta(hours=2)).save()
    Customer(name="Parceiro", phone="5562911110002", created_at=now - timedelta(hours=30), human_operator=True).save()
    Customer(name="Qualificado", phone="5562911110003", created_at=now - timedelta(hours=30), customer_state_now="QUALIFIED").save()
    Customer(name="Antigo", phone="5562911110004", created_at=now - timedelta(hours=30)).save()  # fora do funil zerado

    service = CrmContainer.get_sdr_task_service()
    assert service.create_stale_lead_tasks(now=now) == 1
    assert SdrTask.objects.get().customer.id == stale.id
    assert service.create_stale_lead_tasks(now=now + timedelta(hours=1)) == 0


@pytest.mark.django_db
def test_beat_schedule_points_to_registered_task():
    from django.conf import settings
    from nucleus.celery import app
    import crm.tasks  # noqa: F401
    import sales.tasks  # noqa: F401
    import agenda.tasks  # noqa: F401
    for entry in settings.CELERY_BEAT_SCHEDULE.values():
        assert entry["task"] in app.tasks
