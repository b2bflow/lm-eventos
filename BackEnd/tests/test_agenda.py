"""Agenda da Erica: agendamento pelo card, espelho do Google, bloqueios fixos e lembretes."""
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from agenda.models import CalendarEvent
from agenda.services.agenda_service import AgendaService
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.log_service_model import ServiceLog


class FakeGoogle:
    def __init__(self):
        self.created, self.deleted, self.updated = [], [], []
        self.items, self.next_token = [], "sync-1"

    def create_event(self, title, start, end, description="", location="", with_meet=False, attendees=None):
        self.created.append({"title": title, "with_meet": with_meet, "location": location})
        return {"id": f"g{len(self.created)}", "hangoutLink": "https://meet.google.com/abc-defg-hij" if with_meet else None}

    def update_event(self, google_event_id, **changes):
        self.updated.append((google_event_id, changes))
        return {"id": google_event_id}

    def delete_event(self, google_event_id):
        self.deleted.append(google_event_id)

    def list_events(self, time_min=None, sync_token=None):
        return self.items, self.next_token


@pytest.fixture(autouse=True)
def frozen_now():
    """Os agendamentos dos testes são na semana de 19/10/2026 (agendar no passado é recusado)."""
    with freeze_time("2026-10-19 12:00:00"):
        yield


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr("agenda.services.agenda_service.is_configured", lambda: True)
    monkeypatch.setattr("agenda.controllers.service", AgendaService(google=fake))
    return fake


@pytest.fixture
def lead():
    return Customer(name="Paula Souza", phone="5562955554444", email="paula@acme.test").save()


@pytest.fixture
def erica_phone():
    cfg = LmSettings.get()
    cfg.erica_phone = "5562900000002"
    cfg.save()


@pytest.mark.django_db
def test_online_meeting_from_card_creates_google_event_with_meet_and_notifies_client(api_client, google, lead, zapi_outbox):
    resp = api_client.post("/api/v1/agenda/events/", {
        "type": "reuniao_online", "customer_id": str(lead.id),
        "start": "2026-10-20T14:00:00Z", "end": "2026-10-20T15:00:00Z",
    }, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["meet_link"] == "https://meet.google.com/abc-defg-hij"
    assert resp.data["google_event_id"] == "g1" and resp.data["sync_status"] == "sincronizado"
    assert google.created[0]["with_meet"] is True

    lead.reload()
    assert "reuniao_agendada" in lead.flags
    assert ServiceLog.objects(customer=lead, action_type="MEETING_SCHEDULED").count() == 1
    msg = [m for m in zapi_outbox if m.get("phone") == lead.phone][0]["message"]
    assert "meet.google.com" in msg and "20/10/2026 às 11:00" in msg  # 14h UTC = 11h em Brasília
    assert all(ord(ch) < 0x1F000 for ch in msg)


@pytest.mark.django_db
def test_without_google_event_stays_local_with_warning(api_client, lead):
    resp = api_client.post("/api/v1/agenda/events/", {
        "type": "evento_confirmado", "customer_id": str(lead.id),
        "start": "2026-11-07T20:00:00Z", "end": "2026-11-08T03:00:00Z",
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["sync_status"] == "local"
    assert any("não conectado" in w for w in resp.data["warnings"])


@pytest.mark.django_db
def test_technical_visit_requires_address(api_client, google, lead):
    body = {"type": "visita_tecnica", "customer_id": str(lead.id), "start": "2026-10-21T13:00:00Z", "end": "2026-10-21T14:00:00Z"}
    assert api_client.post("/api/v1/agenda/events/", body, format="json").status_code == 400
    resp = api_client.post("/api/v1/agenda/events/", {**body, "location": "Rua 10, Setor Oeste"}, format="json")
    assert resp.status_code == 201 and google.created[-1]["location"] == "Rua 10, Setor Oeste"


@pytest.mark.django_db
def test_week_view_includes_fixed_training_blocks_and_flags_conflict(api_client, google, lead):
    # Quarta 21/10/2026, 12h em Brasília = 15h UTC
    week = api_client.get("/api/v1/agenda/events/", {"start": "2026-10-19T03:00:00Z", "end": "2026-10-26T03:00:00Z"}).data
    blocks = [e for e in week if e.get("fixed")]
    assert {b["start"] for b in blocks} == {"2026-10-21T15:00:00", "2026-10-23T15:00:00"}

    body = {"type": "reuniao_online", "customer_id": str(lead.id),
            "start": "2026-10-21T15:00:00Z", "end": "2026-10-21T16:00:00Z"}
    # Horário do treino é bloqueio fixo: reunião é recusada e o cliente não recebe confirmação.
    resp = api_client.post("/api/v1/agenda/events/", body, format="json")
    assert resp.status_code == 409 and "Treino" in resp.data["detail"] and resp.data["can_force"] is True
    assert not CalendarEvent.objects(type="reuniao_online").count() and google.created == []

    # A Erica (admin) pode agendar mesmo assim; fica o aviso do conflito.
    resp = api_client.post("/api/v1/agenda/events/", {**body, "force": True}, format="json")
    assert resp.status_code == 201
    assert any("Treino" in w for w in resp.data["warnings"])


@pytest.mark.django_db
def test_sync_brings_google_events_and_cancellations(api_client, google):
    google.items = [
        {"id": "x1", "status": "confirmed", "summary": "Dentista", "start": {"dateTime": "2026-10-22T10:00:00-03:00"},
         "end": {"dateTime": "2026-10-22T11:00:00-03:00"}},
        {"id": "x2", "status": "confirmed", "summary": "Feriado", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}},
    ]
    assert api_client.post("/api/v1/agenda/google/sync/").data == {"created": 2, "updated": 0, "removed": 0}
    event = CalendarEvent.objects.get(google_event_id="x1")
    assert event.start == datetime(2026, 10, 22, 13, 0) and event.type == "externo"
    # Dia inteiro: meia-noite de Brasília (03h UTC), não meia-noite UTC (que cairia às 21h do dia anterior).
    holiday = CalendarEvent.objects.get(google_event_id="x2")
    assert (holiday.start, holiday.end) == (datetime(2026, 11, 2, 3, 0), datetime(2026, 11, 3, 3, 0))
    assert LmSettings.get().google_sync_token == "sync-1"

    google.items = [{"id": "x1", "status": "cancelled"}]
    assert api_client.post("/api/v1/agenda/google/sync/").data["removed"] == 1
    assert CalendarEvent.objects.get(google_event_id="x1").status == "cancelado"


@pytest.mark.django_db
def test_cancel_removes_from_google_and_clears_flag(api_client, google, lead):
    event = api_client.post("/api/v1/agenda/events/", {
        "type": "reuniao_online", "customer_id": str(lead.id),
        "start": "2026-10-20T14:00:00Z", "end": "2026-10-20T15:00:00Z"}, format="json").data
    api_client.delete(f"/api/v1/agenda/events/{event['id']}/")
    assert google.deleted == ["g1"]
    lead.reload()
    assert "reuniao_agendada" not in lead.flags


@pytest.mark.django_db
def test_reminders_24h_and_2h_sent_once(lead, erica_phone, zapi_outbox):
    now = datetime(2026, 10, 19, 12, 0)
    CalendarEvent(type="reuniao_online", title="Reunião", customer=lead, start=now + timedelta(hours=20),
                  end=now + timedelta(hours=21), meet_link="https://meet.google.com/x").save()
    service = AgendaService(google=FakeGoogle())
    assert service.send_reminders(now=now) == 2  # 24h: Erica + cliente
    assert service.send_reminders(now=now) == 0
    assert service.send_reminders(now=now + timedelta(hours=19)) == 2  # 2h: Erica + cliente
    phones = [m["phone"] for m in zapi_outbox]
    assert phones.count("5562900000002") == 2 and phones.count(lead.phone) == 2


@pytest.mark.django_db
def test_confirmed_event_feeds_dashboard_occupancy(api_client, lead):
    soon = datetime.utcnow() + timedelta(days=5)
    CalendarEvent(type="evento_confirmado", title="Show", start=soon, end=soon + timedelta(hours=5)).save()
    resp = api_client.get("/api/v1/analytics/dashboard/metrics/")
    assert resp.data["upcoming_events_count"] == 1
    assert resp.data["schedule_occupancy_rate"] == round(1 / 30 * 100, 2)


@pytest.mark.django_db
def test_google_connect_admin_only_and_callback_rejects_bad_state(api_client, monkeypatch):
    from rest_framework.test import APIClient
    from users.models.user_model import User
    sdr = APIClient()
    sdr.force_authenticate(User.objects.create_user(username="sdr", password="x"))
    assert sdr.get("/api/v1/agenda/google/connect/").status_code == 403
    assert APIClient().get("/api/v1/agenda/google/callback/", {"state": "forjado", "code": "x"}).status_code == 400
    status_data = api_client.get("/api/v1/agenda/google/status/").data
    assert status_data["connected"] is False and status_data["client_configured"] is False


@pytest.mark.django_db
def test_edit_moves_meeting_in_google_and_tells_client(api_client, google, lead, zapi_outbox):
    event = api_client.post("/api/v1/agenda/events/", {
        "type": "reuniao_online", "customer_id": str(lead.id), "notify_customer": False,
        "start": "2026-10-20T14:00:00Z", "end": "2026-10-20T15:00:00Z"}, format="json").data
    CalendarEvent.objects(id=event["id"]).update(set__reminders_sent=["24h_erica"])

    resp = api_client.patch(f"/api/v1/agenda/events/{event['id']}/", {
        "start": "2026-10-22T17:00:00Z", "end": "2026-10-22T18:00:00Z", "title": "Reunião remarcada",
        "notes": "Levar catálogo"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["start"] == "2026-10-22T17:00:00" and resp.data["notes"] == "Levar catálogo"
    google_id, changes = google.updated[0]
    assert google_id == "g1" and changes["title"] == "Reunião remarcada"
    assert changes["start"] == datetime(2026, 10, 22, 17, 0) and "Levar catálogo" in changes["description"]
    assert CalendarEvent.objects.get(id=event["id"]).reminders_sent == []
    assert "remarcada para 22/10/2026 às 14:00" in [m for m in zapi_outbox if m.get("phone") == lead.phone][-1]["message"]

    # Só o título: não mexe no horário nem avisa o cliente de novo.
    sent = len(zapi_outbox)
    api_client.patch(f"/api/v1/agenda/events/{event['id']}/", {"title": "Reunião final"}, format="json")
    assert google.updated[-1][1] == {"title": "Reunião final"} and len(zapi_outbox) == sent


@pytest.mark.django_db
def test_edit_respects_conflicts_and_google_events_are_read_only(api_client, google, lead):
    event = api_client.post("/api/v1/agenda/events/", {
        "type": "reuniao_online", "customer_id": str(lead.id), "notify_customer": False,
        "start": "2026-10-20T14:00:00Z", "end": "2026-10-20T15:00:00Z"}, format="json").data
    treino = {"start": "2026-10-21T15:00:00Z", "end": "2026-10-21T16:00:00Z"}
    assert api_client.patch(f"/api/v1/agenda/events/{event['id']}/", treino, format="json").status_code == 409
    assert google.updated == []

    external = CalendarEvent(type="externo", source="google", google_event_id="x9", title="Dentista",
                             start=datetime(2026, 10, 23, 13), end=datetime(2026, 10, 23, 14)).save()
    resp = api_client.patch(f"/api/v1/agenda/events/{external.id}/", {"title": "Outro"}, format="json")
    assert resp.status_code == 403 and google.updated == []
    assert CalendarEvent.objects.get(id=external.id).title == "Dentista"
