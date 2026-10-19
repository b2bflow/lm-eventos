"""B1/B2: menu e cliques salvos na conversa, mídia com tipo/URL e contexto da IA inalterado."""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from chat.repositories.message_repository import MessageRepository
from crm.models.custumer_model import Customer

URL = "/api/v1/gateway/webhook/zapi/?token=test-webhook-token"
PHONE = "5562999990000"


def base(**extra):
    return {"phone": PHONE, "isGroup": False, "status": "RECEIVED", "senderName": "Ana", **extra}


def click(button_id, label):
    return base(buttonsResponseMessage={"buttonId": button_id, "message": label})


@pytest.fixture
def ai_task():
    with patch("events.tasks.trigger_ai_agent_task.apply_async") as task:
        yield task


def post(payload):
    resp = APIClient().post(URL, payload, format="json")
    assert resp.status_code == 200, resp.data
    return resp


@pytest.mark.django_db
def test_first_message_creates_conversation_and_saves_welcome_menu(ai_task, zapi_outbox):
    post(base(text={"message": "Olá"}))

    customer = Customer.objects.get(phone=PHONE)
    assert customer.new_service is False
    conversation = ConversationModel.objects.get(customer=customer)
    messages = list(MessageModel.objects(conversation=conversation).order_by("created_at"))

    assert [m.direction for m in messages] == ["INCOMING", "OUTGOING"]
    assert messages[0].content == "Olá"
    assert messages[1].content.startswith("Olá bem vindo, a LM Eventos")
    assert messages[1].raw_metadata["buttons"][0]["label"] == "Solicitar orçamento"
    # O que a plataforma grava do menu fica fora do contexto da IA (a produção não gravava).
    assert messages[1].hidden_from_ai is True
    assert conversation.unread_count == 1
    assert zapi_outbox[-1]["buttons"]
    ai_task.assert_not_called()


@pytest.mark.django_db
def test_menu_clicks_and_submenus_are_saved_without_reaching_ai(ai_task):
    post(base(text={"message": "Olá"}))
    post(click("1", "Solicitar orçamento"))
    post(click("5", "Evento Social"))
    ai_task.assert_not_called()

    conversation = ConversationModel.objects.get()
    messages = list(MessageModel.objects(conversation=conversation).order_by("created_at"))
    # Olá, boas-vindas, clique 1, submenu, clique 5, submenu de formatos
    assert len(messages) == 6
    assert messages[3].raw_metadata["buttons"][0]["label"] == "Evento Social"
    assert messages[5].raw_metadata["buttons"][0]["label"] == "Casamento"
    assert [m.hidden_from_ai for m in messages] == [False, True, False, True, False, True]
    assert conversation.last_message_content.startswith("Qual formato de evento social")


@pytest.mark.django_db
def test_image_is_saved_with_type_and_url_and_keeps_ai_content(ai_task):
    post(base(text={"message": "Olá"}))
    post(click("6", "Evento Social"))
    post(base(image={"imageUrl": "https://cdn.z-api.io/img.jpg", "caption": "Meu palco"}))

    msg = MessageModel.objects.order_by("-created_at").first()
    assert msg.message_type == "image"
    assert msg.media_url == "https://cdn.z-api.io/img.jpg"
    assert msg.content == "<image-url>https://cdn.z-api.io/img.jpg</image-url> Meu palco"
    assert ConversationModel.objects.get().last_message_content == "[Imagem] Meu palco"


@pytest.mark.django_db
def test_document_is_saved_as_file(ai_task):
    post(base(text={"message": "Olá"}))
    post(base(document={"documentUrl": "https://cdn.z-api.io/rider.pdf", "fileName": "rider.pdf"}))
    msg = MessageModel.objects(direction="INCOMING").order_by("-created_at").first()
    assert (msg.message_type, msg.media_url) == ("file", "https://cdn.z-api.io/rider.pdf")
