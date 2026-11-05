"""Link da reunião online enviado ao cliente 1 h antes (pedido do João, 05/11/2026)."""
from datetime import datetime, timedelta

import pytest

from agenda.models import CalendarEvent
from agenda.services.agenda_service import AgendaService, meeting_link_message
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings

LINK = "https://meet.google.com/abc-defg-hij"
ERICA = "5562900000002"
# 05/11/2026 17:00 UTC = 14:00 em Brasília
START = datetime(2026, 11, 5, 17, 0)


@pytest.fixture
def lead():
    return Customer(name="Paula Souza", phone="5562955554444").save()


@pytest.fixture(autouse=True)
def erica_phone(db):
    cfg = LmSettings.get()
    cfg.erica_phone = ERICA
    cfg.save()


def meeting(lead, start=START, link=LINK, event_type="reuniao_online", **extra):
    return CalendarEvent(type=event_type, title="Reunião", customer=lead, start=start,
                         end=start + timedelta(minutes=40), meet_link=link, **extra).save()


def client_msgs(outbox, lead):
    return [m["message"] for m in outbox if m.get("phone") == lead.phone]


def erica_msgs(outbox):
    return [m["message"] for m in outbox if m.get("phone") == ERICA]


def test_message_is_the_requested_text():
    assert meeting_link_message("Paula Souza", START, LINK, START - timedelta(hours=1)) == (
        "Boa tarde Paula! Tudo bem?\n"
        "\n"
        "Para facilitar seu acesso a nossa reunião de hoje as 14:00 segue link da call\n"
        "\n"
        "https://meet.google.com/abc-defg-hij\n"
        "\n"
        "Qualquer coisa só chamar!"
    )


@pytest.mark.parametrize("utc_now, greeting", [
    (datetime(2026, 11, 5, 12, 0), "Bom dia"),     # 09:00 em Brasília
    (datetime(2026, 11, 5, 14, 59), "Bom dia"),    # 11:59
    (datetime(2026, 11, 5, 15, 0), "Boa tarde"),   # 12:00
    (datetime(2026, 11, 5, 21, 0), "Boa noite"),   # 18:00
])
def test_greeting_follows_the_time_of_sending(utc_now, greeting):
    text = meeting_link_message("Paula", utc_now + timedelta(hours=1), LINK, utc_now)
    assert text.startswith(f"{greeting} Paula! Tudo bem?")


def test_placeholder_or_missing_name_and_meeting_after_midnight():
    assert meeting_link_message("WhatsApp 5562", START, LINK, START - timedelta(hours=1)).startswith("Boa tarde! Tudo bem?")
    assert meeting_link_message(None, START, LINK, START - timedelta(hours=1)).startswith("Boa tarde! Tudo bem?")
    # 23:30 de Brasília, reunião às 00:30: "de amanhã"
    text = meeting_link_message("Paula", datetime(2026, 11, 6, 3, 30), LINK, datetime(2026, 11, 6, 2, 30))
    assert "reunião de amanhã as 00:30" in text and text.startswith("Boa noite Paula!")


@pytest.mark.django_db
def test_link_sent_once_one_hour_before_whole_and_recorded_in_chat(lead, zapi_outbox, monkeypatch):
    splits = []
    from gateway.adapters.zapi_adapter import ZAPIClient
    original = ZAPIClient.send_message

    def tracking(self, phone, message, split=True):
        splits.append(split)
        self.last_sent_ids = ["zapi-1"]
        return original(self, phone, message, split)

    monkeypatch.setattr(ZAPIClient, "send_message", tracking)
    conversation = ConversationModel(customer=lead).save()
    event = meeting(lead, reminders_sent=["24h_cliente", "24h_erica", "2h_erica"])
    service = AgendaService()

    assert service.send_reminders(now=START - timedelta(minutes=61)) == 0
    assert client_msgs(zapi_outbox, lead) == []

    assert service.send_reminders(now=START - timedelta(minutes=58)) == 1
    assert client_msgs(zapi_outbox, lead) == [meeting_link_message("Paula Souza", START, LINK, START - timedelta(minutes=58))]
    assert splits == [False]  # sai inteira, com as quebras de linha
    assert "1h_cliente" in CalendarEvent.objects.get(id=event.id).reminders_sent

    assert service.send_reminders(now=START - timedelta(minutes=50)) == 0
    assert len(client_msgs(zapi_outbox, lead)) == 1

    saved = MessageModel.objects(conversation=conversation).get()
    assert saved.direction == "OUTGOING" and "segue link da call" in saved.content
    assert saved.raw_metadata["automatic"] == "link_reuniao"
    assert saved.raw_metadata["zapi_message_ids"] == ["zapi-1"]  # pode ser apagada para todos


@pytest.mark.django_db
def test_online_meeting_client_gets_the_link_instead_of_the_2h_reminder(lead, zapi_outbox):
    meeting(lead, reminders_sent=["24h_cliente", "24h_erica"])
    service = AgendaService()
    assert service.send_reminders(now=START - timedelta(minutes=110)) == 1  # só a Erica (2 h)
    assert client_msgs(zapi_outbox, lead) == []
    assert service.send_reminders(now=START - timedelta(minutes=55)) == 1  # link para o cliente
    assert len(client_msgs(zapi_outbox, lead)) == 1 and "segue link da call" in client_msgs(zapi_outbox, lead)[0]


@pytest.mark.django_db
def test_technical_visit_keeps_the_2h_reminder_and_gets_no_link(lead, zapi_outbox):
    meeting(lead, event_type="visita_tecnica", link=None, location="Rua A, 1",
            reminders_sent=["24h_cliente", "24h_erica"])
    service = AgendaService()
    assert service.send_reminders(now=START - timedelta(minutes=110)) == 2
    assert service.send_reminders(now=START - timedelta(minutes=55)) == 0
    assert [m.startswith("Lembrete: sua visita técnica") for m in client_msgs(zapi_outbox, lead)] == [True]


@pytest.mark.django_db
def test_without_link_erica_is_warned_once_and_link_added_later_is_sent(lead, zapi_outbox):
    event = meeting(lead, link=None, reminders_sent=["24h_cliente", "24h_erica", "2h_erica"])
    service = AgendaService()
    assert service.send_reminders(now=START - timedelta(minutes=58)) == 1
    assert service.send_reminders(now=START - timedelta(minutes=53)) == 0
    warnings = erica_msgs(zapi_outbox)
    assert len(warnings) == 1 and "não tem link" in warnings[0] and "Paula Souza" in warnings[0]
    assert client_msgs(zapi_outbox, lead) == []

    CalendarEvent.objects(id=event.id).update(set__meet_link=LINK)
    assert service.send_reminders(now=START - timedelta(minutes=40)) == 1
    assert LINK in client_msgs(zapi_outbox, lead)[0]


@pytest.mark.django_db
def test_failed_send_warns_erica_and_is_not_retried(lead, zapi_outbox, monkeypatch):
    from gateway.adapters.zapi_adapter import ZAPIClient

    def client_phone_fails(self, phone, message, split=True):
        zapi_outbox.append({"phone": phone, "message": message})
        return phone == ERICA

    monkeypatch.setattr(ZAPIClient, "send_message", client_phone_fails)
    meeting(lead, reminders_sent=["24h_cliente", "24h_erica", "2h_erica"])
    service = AgendaService()
    assert service.send_reminders(now=START - timedelta(minutes=58)) == 0
    assert service.send_reminders(now=START - timedelta(minutes=53)) == 0
    warnings = erica_msgs(zapi_outbox)
    assert len(warnings) == 1 and "Não foi possível enviar o link" in warnings[0] and LINK in warnings[0]


@pytest.mark.django_db
def test_cancelled_started_or_leadless_meetings_get_nothing(lead, zapi_outbox):
    meeting(lead, status="cancelado", reminders_sent=["24h_cliente", "24h_erica", "2h_erica"])
    meeting(None, reminders_sent=["24h_erica", "2h_erica"])
    meeting(lead, start=START - timedelta(minutes=70), reminders_sent=["24h_cliente", "24h_erica", "2h_erica"])
    assert AgendaService().send_reminders(now=START - timedelta(minutes=58)) == 0
    assert zapi_outbox == []
