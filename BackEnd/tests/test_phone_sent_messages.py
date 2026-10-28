"""Mensagens que a equipe manda direto pelo WhatsApp (Z-API "Notificar as enviadas por mim também")."""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer

URL = "/api/v1/gateway/webhook/zapi/?token=test-webhook-token"
PHONE = "5562999990000"


def incoming(text, **extra):
    return {"phone": PHONE, "isGroup": False, "status": "RECEIVED", "senderName": "Ana",
            "fromMe": False, "text": {"message": text}, **extra}


def from_phone(text=None, message_id=None, **extra):
    """Envio feito no celular da LM: fromMe=True, fromApi=False; senderName é o nome da própria LM."""
    payload = {"phone": PHONE, "isGroup": False, "status": "SENT", "fromMe": True, "fromApi": False,
               "senderName": "LM Eventos", "chatName": "Ana Cliente", **extra}
    if text is not None:
        payload["text"] = {"message": text}
    if message_id:
        payload["messageId"] = message_id
    return payload


@pytest.fixture
def ai_task():
    with patch("events.tasks.trigger_ai_agent_task.apply_async") as task:
        yield task


@pytest.fixture
def ai_on():
    with patch("chat.services.message_service.SystemConfigRepository.get_config") as cfg:
        cfg.return_value.ai_active = True
        yield


def post(payload):
    resp = APIClient().post(URL, payload, format="json")
    assert resp.status_code == 200, resp.data
    return resp


def ai_conversation():
    """Cliente já passou pelo menu e está com a IA."""
    post(incoming("Olá"))
    conversation = ConversationModel.objects.get()
    assert conversation.tag == "AGENTE" and conversation.ai_active is True
    Customer.objects.update(set__send_button=False)
    return conversation


@pytest.mark.django_db
def test_phone_reply_is_saved_and_moves_conversation_from_ai_to_operator(ai_task, ai_on):
    conversation = ai_conversation()

    post(from_phone("Oi Ana, aqui é a Erica. Já te ligo!", message_id="ABC1"))

    conversation.reload()
    assert conversation.tag == "OPERADOR"
    assert conversation.ai_active is False
    assert conversation.needs_attention is False
    assert conversation.last_message_content == "Oi Ana, aqui é a Erica. Já te ligo!"

    sent = MessageModel.objects(external_id="ABC1").get()
    assert sent.direction == "OUTGOING"
    assert sent.role == "OPERATOR"
    assert sent.hidden_from_ai is False
    assert sent.raw_metadata["sent_from_phone"] is True

    event = MessageModel.objects(direction="INTERNAL").order_by("-created_at").first()
    assert "direto pelo WhatsApp" in event.content
    assert event.raw_metadata["mode"] == "OPERADOR"

    # Próxima mensagem do cliente fica com o operador: a IA não responde.
    ai_task.reset_mock()
    post(incoming("Combinado"))
    ai_task.assert_not_called()
    conversation.reload()
    assert conversation.needs_attention is True


@pytest.mark.django_db
def test_messages_sent_by_the_platform_api_are_not_duplicated(ai_task):
    conversation = ai_conversation()
    before = MessageModel.objects.count()

    post(from_phone("Olá bem vindo, a LM Eventos", message_id="API1", fromApi=True))

    assert MessageModel.objects.count() == before
    conversation.reload()
    assert conversation.tag == "AGENTE" and conversation.ai_active is True


@pytest.mark.django_db
def test_echo_without_from_api_flag_is_recognised_by_text(ai_task):
    conversation = ai_conversation()
    before = MessageModel.objects.count()
    # Trecho do menu de boas-vindas que a plataforma acabou de mandar (independe do nome da assistente).
    payload = from_phone("vou dar início ao seu atendimento")
    payload.pop("fromApi")

    post(payload)

    assert MessageModel.objects.count() == before
    conversation.reload()
    assert conversation.tag == "AGENTE"


@pytest.mark.django_db
def test_phone_message_to_new_number_creates_contact_with_chat_name(ai_task):
    post(from_phone("Bom dia! Segue o orçamento que conversamos."))

    customer = Customer.objects.get(phone=PHONE)
    assert customer.name == "Ana Cliente"
    conversation = ConversationModel.objects.get(customer=customer)
    assert conversation.tag == "OPERADOR" and conversation.ai_active is False
    assert MessageModel.objects(direction="OUTGOING", role="OPERATOR").count() == 1


@pytest.mark.django_db
def test_same_short_text_from_customer_and_team_are_both_kept(ai_task):
    ai_conversation()
    post(from_phone("ok", message_id="T1"))
    post(incoming("ok", messageId="C1"))

    texts = [(m.direction, m.content) for m in MessageModel.objects(content="ok")]
    assert sorted(texts) == [("INCOMING", "ok"), ("OUTGOING", "ok")]


@pytest.mark.django_db
def test_redelivered_phone_message_is_saved_once(ai_task):
    ai_conversation()
    post(from_phone("Te mando o PDF já já", message_id="DUP1"))
    post(from_phone("Te mando o PDF já já", message_id="DUP1"))
    assert MessageModel.objects(external_id="DUP1").count() == 1


@pytest.mark.django_db
def test_groups_reactions_and_status_are_ignored(ai_task):
    conversation = ai_conversation()
    before = MessageModel.objects.count()

    post(from_phone("oi grupo", isGroup=True, phone="120363000000000000-group"))
    post(from_phone("status", phone="status@broadcast"))
    post(from_phone(reaction={"value": "👍", "referencedMessage": {"messageId": "X"}}))

    assert MessageModel.objects.count() == before
    conversation.reload()
    assert conversation.tag == "AGENTE"


@pytest.mark.django_db
def test_phone_media_keeps_type_url_and_caption(ai_task):
    ai_conversation()
    post(from_phone(image={"imageUrl": "https://cdn.z-api.io/palco.jpg", "caption": "Palco montado"}, message_id="IMG1"))
    post(from_phone(document={"documentUrl": "https://cdn.z-api.io/proposta.pdf", "fileName": "proposta.pdf"},
                    message_id="DOC1"))
    post(from_phone(video={"videoUrl": "https://cdn.z-api.io/v.mp4"}, message_id="VID1"))

    image = MessageModel.objects(external_id="IMG1").get()
    assert (image.message_type, image.media_url, image.content) == ("image", "https://cdn.z-api.io/palco.jpg", "Palco montado")
    doc = MessageModel.objects(external_id="DOC1").get()
    assert (doc.message_type, doc.content) == ("file", "[Arquivo] proposta.pdf")
    video = MessageModel.objects(external_id="VID1").get()
    assert (video.message_type, video.content) == ("video", "[Vídeo]")


@pytest.mark.django_db
def test_phone_audio_is_transcribed(ai_task):
    ai_conversation()
    with patch("gateway.service.audio_transcription_service.AudioTranscriptionService.transcribe",
               return_value="Oi Ana, tudo certo para sábado"):
        post(from_phone(audio={"audioUrl": "https://cdn.z-api.io/a.ogg"}, message_id="AUD1"))

    audio = MessageModel.objects(external_id="AUD1").get()
    assert (audio.message_type, audio.content) == ("audio", "Oi Ana, tudo certo para sábado")


@pytest.mark.django_db
def test_conversation_already_with_operator_gets_no_new_handover_event(ai_task):
    conversation = ai_conversation()
    post(from_phone("Primeira", message_id="P1"))
    post(from_phone("Segunda", message_id="P2"))

    events = MessageModel.objects(direction="INTERNAL", raw_metadata__mode="OPERADOR")
    assert events.count() == 1
    conversation.reload()
    assert conversation.tag == "OPERADOR"
