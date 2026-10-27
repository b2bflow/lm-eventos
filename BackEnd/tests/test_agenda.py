"""Agenda da Erica: agendamento pelo card, espelho do Google, eventos que se repetem e lembretes."""
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from agenda.models import CalendarEvent, EventSeries
from agenda.services.agenda_service import AgendaService
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.log_service_model import ServiceLog


class FakeGoogle:
    def __init__(self):
        self.created, self.deleted, self.updated = [], [], []
        self.items, self.next_token = [], "sync-1"

    def create_event(self, title, start, end, description="", location="", with_meet=False, attendees=None,
                     all_day=False, recurrence=None):
        self.created.append({"title": title, "with_meet": with_meet, "location": location, "start": start, "end": end,
                             "all_day": all_day, "recurrence": recurrence})
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
def test_training_is_a_weekly_block_created_by_hand_and_flags_conflict(api_client, google, lead):
    # Sem bloqueio embutido: a semana começa vazia.
    week_range = {"start": "2026-10-19T03:00:00Z", "end": "2026-10-26T03:00:00Z"}
    assert api_client.get("/api/v1/agenda/events/", week_range).data == []

    # Treino quarta e sexta 12h (Brasília = 15h UTC), criado como bloqueio que se repete.
    resp = api_client.post("/api/v1/agenda/events/", {
        "type": "bloqueio", "title": "Treino", "start": "2026-10-21T15:00:00Z", "end": "2026-10-21T16:00:00Z",
        "recurrence": {"freq": "weekly", "by_weekday": [2, 4]}}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["recurrence"]["by_weekday"] == [2, 4] and resp.data["series_id"]
    week = api_client.get("/api/v1/agenda/events/", week_range).data
    assert {e["start"] for e in week} == {"2026-10-21T15:00:00", "2026-10-23T15:00:00"}

    body = {"type": "reuniao_online", "customer_id": str(lead.id),
            "start": "2026-10-21T15:00:00Z", "end": "2026-10-21T16:00:00Z"}
    # Horário do treino: reunião é recusada e o cliente não recebe confirmação.
    resp = api_client.post("/api/v1/agenda/events/", body, format="json")
    assert resp.status_code == 409 and "Treino" in resp.data["detail"] and resp.data["can_force"] is True
    assert not CalendarEvent.objects(type="reuniao_online").count() and len(google.created) == 1

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
    api_client.post("/api/v1/agenda/events/", {"type": "bloqueio", "title": "Treino", **treino}, format="json")
    assert api_client.patch(f"/api/v1/agenda/events/{event['id']}/", treino, format="json").status_code == 409
    assert google.updated == []

    external = CalendarEvent(type="externo", source="google", google_event_id="x9", title="Dentista",
                             start=datetime(2026, 10, 23, 13), end=datetime(2026, 10, 23, 14)).save()
    resp = api_client.patch(f"/api/v1/agenda/events/{external.id}/", {"title": "Outro"}, format="json")
    assert resp.status_code == 403 and google.updated == []
    assert CalendarEvent.objects.get(id=external.id).title == "Dentista"


@pytest.mark.django_db
def test_disconnect_revokes_token_and_drops_google_mirror_only(api_client, google, monkeypatch):
    revoked = []
    monkeypatch.setattr("agenda.services.agenda_service.revoke_token", lambda token: revoked.append(token) or True)
    cfg = LmSettings.get()
    cfg.google_refresh_token, cfg.google_sync_token = "1//tok", "sync-9"
    cfg.save()
    CalendarEvent(type="externo", source="google", google_event_id="x1", title="Dentista",
                  start=datetime(2026, 10, 23, 13), end=datetime(2026, 10, 23, 14)).save()
    mine = CalendarEvent(type="bloqueio", title="Bloqueio", google_event_id="g7",
                         start=datetime(2026, 10, 23, 15), end=datetime(2026, 10, 23, 16)).save()

    resp = api_client.post("/api/v1/agenda/google/disconnect/")
    assert resp.status_code == 200 and resp.data == {"disconnected": True, "mirror_removed": 1}
    assert revoked == ["1//tok"]
    cfg.reload()
    assert (cfg.google_refresh_token, cfg.google_sync_token) == ("", "")
    assert [e.id for e in CalendarEvent.objects] == [mine.id]
    assert api_client.post("/api/v1/agenda/google/disconnect/").status_code == 400


@pytest.mark.django_db
def test_auto_sync_switch_is_admin_only_and_pauses_the_beat(api_client, google, monkeypatch):
    from rest_framework.test import APIClient
    from agenda.tasks import sync_google_calendar
    from users.models.user_model import User
    monkeypatch.setattr("agenda.services.google_calendar_client.is_configured", lambda: True)
    sdr = APIClient()
    sdr.force_authenticate(User.objects.create_user(username="sdr2", password="x"))
    assert sdr.patch("/api/v1/agenda/google/status/", {"auto_sync": False}, format="json").status_code == 403
    assert sdr.post("/api/v1/agenda/google/disconnect/").status_code == 403

    resp = api_client.patch("/api/v1/agenda/google/status/", {"auto_sync": False}, format="json")
    assert resp.status_code == 200 and resp.data["auto_sync"] is False
    assert sync_google_calendar() == "sincronizacao-automatica-desligada"

    # Sincronizar pelo botão continua valendo e registra a hora.
    api_client.post("/api/v1/agenda/google/sync/")
    assert api_client.get("/api/v1/agenda/google/status/").data["last_sync_at"] == "2026-10-19T12:00:00"


# --- Eventos que se repetem (como no Google Agenda) -------------------------------------------

def _post(api_client, **body):
    resp = api_client.post("/api/v1/agenda/events/", {"type": "bloqueio", "title": "Treino", **body}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


@pytest.mark.django_db
def test_recurring_event_is_one_google_event_with_rrule_and_local_occurrences(api_client, google):
    # Qua 21/10 às 9h (12h UTC), segunda e quarta a cada 2 semanas, 4 ocorrências.
    first = _post(api_client, start="2026-10-21T12:00:00Z", end="2026-10-21T13:00:00Z",
                  recurrence={"freq": "weekly", "interval": 2, "by_weekday": [0, 2], "count": 4})
    assert len(google.created) == 1
    assert google.created[0]["recurrence"] == ["RRULE:FREQ=WEEKLY;WKST=SU;INTERVAL=2;BYDAY=MO,WE;COUNT=4"]
    occurrences = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")
    # A cada 2 semanas (semana começando no domingo): qua 21/10, seg 2/11, qua 4/11, seg 16/11.
    assert [o.start for o in occurrences] == [datetime(2026, 10, 21, 12), datetime(2026, 11, 2, 12),
                                             datetime(2026, 11, 4, 12), datetime(2026, 11, 16, 12)]
    assert occurrences[1].google_event_id == "g1_20261102T120000Z"
    assert {o.sync_status for o in occurrences} == {"sincronizado"}


@pytest.mark.django_db
def test_rrule_variants_monthly_until_and_all_day():
    from agenda.services import recurrence as rec
    start = datetime(2026, 10, 28, 15)  # quarta, 28/10 12h em Brasília (4ª e última quarta do mês)
    assert rec.to_rrule({"freq": "monthly", "interval": 1, "monthly": "weekday"}, start) == ["RRULE:FREQ=MONTHLY;WKST=SU;BYDAY=4WE"]
    assert rec.to_rrule({"freq": "monthly", "interval": 1, "monthly": "last_weekday"}, start) == ["RRULE:FREQ=MONTHLY;WKST=SU;BYDAY=-1WE"]
    # Até 30/11 23:59:59 em Brasília = 1/12 02:59:59 UTC; em dia inteiro vale a data.
    assert rec.to_rrule({"freq": "daily", "interval": 1, "until": "2026-11-30"}, start) == ["RRULE:FREQ=DAILY;WKST=SU;UNTIL=20261201T025959Z"]
    assert rec.to_rrule({"freq": "yearly", "interval": 1, "until": "2030-01-01"}, start, all_day=True) == ["RRULE:FREQ=YEARLY;WKST=SU;UNTIL=20300101"]
    last_wed = rec.occurrence_starts({"freq": "monthly", "interval": 1, "monthly": "last_weekday", "count": 3}, start,
                                     datetime(2027, 6, 1))
    assert [d.date().isoformat() for d in last_wed] == ["2026-10-28", "2026-11-25", "2026-12-30"]
    with pytest.raises(ValueError):
        rec.clean_rule({"freq": "weekly", "until": "2026-12-01", "count": 3}, start)


@pytest.mark.django_db
def test_all_day_event_uses_dates_in_google(api_client, google):
    event = _post(api_client, type="evento_confirmado", title="Casamento", all_day=True,
                  start="2026-11-07T03:00:00Z", end="2026-11-08T03:00:00Z")
    assert event["all_day"] is True and (event["start"], event["end"]) == ("2026-11-07T03:00:00", "2026-11-08T03:00:00")
    from agenda.services.google_calendar_client import _when
    assert _when(google.created[0]["start"], True) == {"date": "2026-11-07"}
    assert _when(google.created[0]["end"], True) == {"date": "2026-11-08"}


@pytest.mark.django_db
def test_edit_only_this_occurrence_patches_the_google_instance(api_client, google):
    first = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z",
                  recurrence={"freq": "weekly", "by_weekday": [2]})
    second = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")[1]
    resp = api_client.patch(f"/api/v1/agenda/events/{second.id}/", {
        "start": "2026-10-28T17:00:00Z", "end": "2026-10-28T18:00:00Z", "scope": "this"}, format="json")
    assert resp.status_code == 200, resp.data
    assert google.updated[-1][0] == "g1_20261028T150000Z"
    assert CalendarEvent.objects(series_id=first["series_id"], start=datetime(2026, 11, 4, 15)).count() == 1
    # Mudar a repetição só desta ocorrência não existe no Google.
    resp = api_client.patch(f"/api/v1/agenda/events/{second.id}/", {
        "scope": "this", "recurrence": {"freq": "daily"}}, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_edit_following_splits_the_series_like_google(api_client, google):
    first = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z",
                  recurrence={"freq": "weekly", "by_weekday": [2], "count": 6})
    third = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")[2]  # 4/11
    resp = api_client.patch(f"/api/v1/agenda/events/{third.id}/", {
        "title": "Treino funcional", "start": "2026-11-04T16:00:00Z", "end": "2026-11-04T17:00:00Z",
        "scope": "following", "recurrence": {"freq": "weekly", "by_weekday": [2], "count": 6}}, format="json")
    assert resp.status_code == 200, resp.data
    # A série antiga para na véspera (3/11) e a nova continua com as 4 ocorrências que faltavam.
    old_id, changes = google.updated[0]
    assert old_id == "g1" and changes["recurrence"] == ["RRULE:FREQ=WEEKLY;WKST=SU;BYDAY=WE;UNTIL=20261104T025959Z"]
    assert google.created[-1]["recurrence"] == ["RRULE:FREQ=WEEKLY;WKST=SU;BYDAY=WE;COUNT=4"]
    old = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")
    assert [o.start.day for o in old] == [21, 28]
    new = CalendarEvent.objects(series_id=resp.data["series_id"]).order_by("start")
    assert new[0].start == datetime(2026, 11, 4, 16) and new.count() == 4
    assert {o.title for o in new} == {"Treino funcional"} and new[0].google_event_id == "g2_20261104T160000Z"


@pytest.mark.django_db
def test_edit_all_moves_every_occurrence_and_patches_the_master(api_client, google):
    first = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z",
                  recurrence={"freq": "weekly", "by_weekday": [2], "count": 3})
    second = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")[1]
    # Muda o título e a hora (12h -> 7h em Brasília) a partir da 2ª ocorrência: vale para todas.
    resp = api_client.patch(f"/api/v1/agenda/events/{second.id}/", {
        "title": "Corrida", "start": "2026-10-28T10:00:00Z", "end": "2026-10-28T11:00:00Z", "scope": "all"}, format="json")
    assert resp.status_code == 200, resp.data
    google_id, changes = google.updated[-1]
    assert google_id == "g1" and changes["start"] == datetime(2026, 10, 21, 10) and changes["title"] == "Corrida"
    occurrences = CalendarEvent.objects(series_id=first["series_id"]).order_by("start")
    assert [(o.start.day, o.start.hour, o.title) for o in occurrences] == [(21, 10, "Corrida"), (28, 10, "Corrida"), (4, 10, "Corrida")]

    # Só o título: atualiza as ocorrências no lugar, sem refazer a série.
    ids = [o.id for o in occurrences]
    api_client.patch(f"/api/v1/agenda/events/{ids[0]}/", {"title": "Corrida leve", "scope": "all"}, format="json")
    assert google.updated[-1] == ("g1", {"title": "Corrida leve"})
    assert [o.id for o in CalendarEvent.objects(series_id=first["series_id"]).order_by("start")] == ids


@pytest.mark.django_db
def test_single_event_can_start_repeating_and_stop_again(api_client, google):
    event = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z")
    resp = api_client.patch(f"/api/v1/agenda/events/{event['id']}/", {
        "recurrence": {"freq": "daily", "count": 3}, "scope": "all"}, format="json")
    assert resp.status_code == 200, resp.data
    # O mesmo evento do Google ganha a regra.
    assert google.updated[-1][0] == "g1" and google.updated[-1][1]["recurrence"] == ["RRULE:FREQ=DAILY;WKST=SU;COUNT=3"]
    assert CalendarEvent.objects(series_id=resp.data["series_id"]).count() == 3
    assert not CalendarEvent.objects(id=event["id"]).count()

    # "Não se repete" em todos: fica só este, e o Google tira a regra do mesmo evento.
    resp = api_client.patch(f"/api/v1/agenda/events/{resp.data['id']}/", {"recurrence": None, "scope": "all"}, format="json")
    assert resp.status_code == 200 and resp.data["series_id"] is None and resp.data["google_event_id"] == "g1"
    assert google.updated[-1][1]["recurrence"] == []
    assert CalendarEvent.objects(type="bloqueio").count() == 1 and not EventSeries.objects.count()


@pytest.mark.django_db
def test_cancel_this_following_and_all(api_client, google):
    first = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z",
                  recurrence={"freq": "weekly", "by_weekday": [2], "count": 5})
    occurrences = list(CalendarEvent.objects(series_id=first["series_id"]).order_by("start"))
    api_client.delete(f"/api/v1/agenda/events/{occurrences[1].id}/?scope=this")
    assert google.deleted == ["g1_20261028T150000Z"]
    api_client.delete(f"/api/v1/agenda/events/{occurrences[3].id}/?scope=following")
    assert google.updated[-1][1]["recurrence"] == ["RRULE:FREQ=WEEKLY;WKST=SU;BYDAY=WE;UNTIL=20261111T025959Z"]
    alive = CalendarEvent.objects(series_id=first["series_id"], status="confirmado").order_by("start")
    assert [o.start.day for o in alive] == [21, 4]
    api_client.delete(f"/api/v1/agenda/events/{occurrences[2].id}/?scope=all")
    assert google.deleted[-1] == "g1"
    assert not CalendarEvent.objects(series_id=first["series_id"], status="confirmado").count()


@pytest.mark.django_db
def test_open_ended_series_is_generated_as_the_agenda_looks_ahead(api_client, google):
    _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z", recurrence={"freq": "daily"})
    assert CalendarEvent.objects.count() == 366
    far = api_client.get("/api/v1/agenda/events/", {"start": "2028-01-03T03:00:00Z", "end": "2028-01-10T03:00:00Z"}).data
    assert len(far) == 7 and far[0]["recurrence"] == {"freq": "daily", "interval": 1, "until": None, "count": None}


@pytest.mark.django_db
def test_sync_keeps_own_series_and_does_not_duplicate_them(api_client, google):
    first = _post(api_client, start="2026-10-21T15:00:00Z", end="2026-10-21T16:00:00Z",
                  recurrence={"freq": "weekly", "by_weekday": [2], "count": 2})
    google.items = [
        # Ocorrência da série com o id do Google diferente do previsto: casa pelo início original.
        {"id": "g1_outro", "recurringEventId": "g1", "status": "confirmed", "summary": "Treino",
         "originalStartTime": {"dateTime": "2026-10-28T12:00:00-03:00"},
         "start": {"dateTime": "2026-10-28T13:00:00-03:00"}, "end": {"dateTime": "2026-10-28T14:00:00-03:00"}},
        # Ocorrência além do que existe aqui, e evento da plataforma que não existe mais: ignorados.
        {"id": "g1_20261104T150000Z", "recurringEventId": "g1", "status": "confirmed", "summary": "Treino",
         "start": {"dateTime": "2026-11-04T12:00:00-03:00"}, "end": {"dateTime": "2026-11-04T13:00:00-03:00"}},
        {"id": "velho", "status": "confirmed", "summary": "Antigo", "extendedProperties": {"private": {"origem": "lm-eventos"}},
         "start": {"dateTime": "2026-10-22T12:00:00-03:00"}, "end": {"dateTime": "2026-10-22T13:00:00-03:00"}},
    ]
    assert api_client.post("/api/v1/agenda/google/sync/").data == {"created": 0, "updated": 1, "removed": 0}
    moved = CalendarEvent.objects.get(google_event_id="g1_outro")
    assert moved.series_id == first["series_id"] and moved.start == datetime(2026, 10, 28, 16)
    assert CalendarEvent.objects.count() == 2
