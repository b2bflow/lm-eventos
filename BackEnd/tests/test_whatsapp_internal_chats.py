"""Aba WhatsApp: lista na ordem da última mensagem (abrir a conversa não a leva para o topo) e
Chats internos (como o Arquivadas do WhatsApp: fora da lista principal e sem IA)."""
from datetime import datetime, timedelta

import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.repositories.conversation_repository import ConversationRepository
from chat.repositories.message_repository import MessageRepository
from crm.models.custumer_model import Customer

LIST = "/api/v1/chat/conversations/"
BASE = datetime(2026, 10, 1, 12, 0, 0)


def make_conv(name, phone, minutes, **fields):
    customer = Customer(name=name, phone=phone).save()
    return ConversationModel(customer=customer, last_message_at=BASE + timedelta(minutes=minutes), **fields).save()


def listed(api_client, **params):
    return [c["customer_name"] for c in api_client.get(LIST, {"status": "OPEN", **params}).data["results"]]


@pytest.mark.django_db
def test_opening_a_conversation_keeps_its_place_and_time(api_client):
    old = make_conv("Antiga", "5562900000001", 0)
    make_conv("Nova", "5562900000002", 10)
    before = api_client.get(LIST, {"status": "OPEN"}).data["results"]
    assert [c["customer_name"] for c in before] == ["Nova", "Antiga"]

    # Clicar na conversa marca como lida (antes isso mudava updated_at e a levava para o topo)
    assert api_client.patch(f"{LIST}{old.id}/", {"mark_read": True}, format="json").status_code == 200
    after = api_client.get(LIST, {"status": "OPEN"}).data["results"]
    assert [c["customer_name"] for c in after] == ["Nova", "Antiga"]
    assert after[1]["last_interaction_at"] == before[1]["last_interaction_at"]


@pytest.mark.django_db
def test_new_message_moves_to_top_but_internal_note_does_not(api_client):
    old = make_conv("Antiga", "5562900000001", 0)
    make_conv("Nova", "5562900000002", 10)

    MessageRepository.create(old, direction="INTERNAL", content="nota", role="note")
    assert listed(api_client) == ["Nova", "Antiga"]

    msg = MessageRepository.create(old, direction="INCOMING", content="Oi")
    assert listed(api_client) == ["Antiga", "Nova"]
    card = api_client.get(LIST, {"status": "OPEN"}).data["results"][0]
    assert card["last_interaction_at"].startswith(msg.created_at.isoformat()[:19])


@pytest.mark.django_db
def test_old_conversations_get_time_of_last_message(api_client):
    customer = Customer(name="Legada", phone="5562900000003").save()
    conv = ConversationModel(customer=customer, updated_at=BASE + timedelta(days=5)).save()
    ConversationModel.objects(id=conv.id).update(unset__last_message_at=True)
    MessageModel(conversation=conv, customer=customer, role="user", direction="INCOMING", content="oi",
                 created_at=BASE).save()
    MessageModel(conversation=conv, customer=customer, role="note", direction="INTERNAL", content="nota",
                 created_at=BASE + timedelta(days=1)).save()
    no_messages = ConversationModel(customer=Customer(name="Vazia", phone="5562900000004").save(),
                                    updated_at=BASE + timedelta(hours=1)).save()

    assert ConversationRepository.fill_missing_last_message_at() == 2
    assert ConversationModel.objects.get(id=conv.id).last_message_at == BASE
    assert ConversationModel.objects.get(id=no_messages.id).last_message_at == BASE + timedelta(hours=1)
    assert ConversationRepository.fill_missing_last_message_at() == 0


@pytest.mark.django_db
def test_move_to_internal_chats_pauses_ai_and_leaves_main_list(api_client, zapi_outbox):
    conv = make_conv("Fornecedor", "5562900000005", 5, tag="AGENTE", ai_active=True, unread_count=2)
    make_conv("Cliente", "5562900000006", 0)

    resp = api_client.post(f"{LIST}{conv.id}/internal/", {"internal": True}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["customer_internal_chat"] is True
    assert resp.data["tag"] == "OPERADOR" and resp.data["ai_active"] is False
    event = MessageModel.objects.get(conversation=conv, direction="INTERNAL")
    assert event.content.startswith("Conversa movida para os Chats internos por erica")
    assert zapi_outbox == []

    main = api_client.get(LIST, {"status": "OPEN"}).data
    assert [c["customer_name"] for c in main["results"]] == ["Cliente"]
    assert main["internal"] == {"total": 1, "unread": 1}
    assert listed(api_client, internal="1") == ["Fornecedor"]
    # A busca acha os internos também, como no WhatsApp
    assert listed(api_client, search="Fornecedor") == ["Fornecedor"]

    # IA não volta enquanto estiver nos Chats internos
    assert api_client.post(f"{LIST}{conv.id}/mode/", {"mode": "AGENTE"}, format="json").status_code == 400

    resp = api_client.post(f"{LIST}{conv.id}/internal/", {"internal": False}, format="json")
    assert resp.status_code == 200 and resp.data["customer_internal_chat"] is False
    assert resp.data["tag"] == "OPERADOR"  # tirar dos internos não religa a IA sozinho
    assert listed(api_client) == ["Fornecedor", "Cliente"]


@pytest.mark.django_db
def test_new_conversation_of_internal_contact_starts_without_ai():
    customer = Customer(name="Equipe", phone="5562900000007", internal_chat=True).save()
    conv = ConversationRepository.create_conversation(str(customer.id))
    assert conv.tag == "OPERADOR" and conv.ai_active is False and conv.last_message_at

    other = Customer(name="Lead", phone="5562900000008").save()
    assert ConversationRepository.create_conversation(str(other.id)).tag == "AGENTE"
