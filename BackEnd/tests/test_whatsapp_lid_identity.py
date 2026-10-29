"""Mesmo contato pelo número e pelo @lid, avisos sem conteúdo e o comando fix_whatsapp_contacts."""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer

URL = "/api/v1/gateway/webhook/zapi/?token=test-webhook-token"
PHONE = "5562999990000"
LID = "203345327304808@lid"
LM_LID = "111111111111111@lid"
PLACEHOLDER = "Olá, Tenho interesse e queria mais informações, por favor."


def incoming(text=None, message_id=None, **extra):
    """Cliente escrevendo: número em phone, lid dele em senderLid/chatLid."""
    payload = {"phone": PHONE, "senderLid": LID, "chatLid": LID, "isGroup": False, "status": "RECEIVED",
               "fromMe": False, "senderName": "Gleidson", "chatName": "Gleidson", **extra}
    if text is not None:
        payload["text"] = {"message": text}
    if message_id:
        payload["messageId"] = message_id
    return payload


def from_phone(text, message_id, **extra):
    """Equipe no celular: a Z-API manda o lid do cliente em phone e o lid da LM em senderLid."""
    return {"phone": LID, "senderLid": LM_LID, "isGroup": False, "status": "SENT", "fromMe": True,
            "fromApi": False, "senderName": "LM Eventos", "chatName": "Gleidson",
            "text": {"message": text}, "messageId": message_id, **extra}


@pytest.fixture(autouse=True)
def ai_task():
    with patch("events.tasks.trigger_ai_agent_task.apply_async") as task:
        yield task


def post(payload):
    resp = APIClient().post(URL, payload, format="json")
    assert resp.status_code == 200, resp.data
    return resp


@pytest.mark.django_db
def test_phone_reply_by_lid_lands_in_the_customer_conversation():
    post(incoming("Amiga, o que aconteceu com você?", "IN1"))
    customer = Customer.objects.get(phone=PHONE)
    assert customer.whatsapp_lid == LID

    post(from_phone("Fiz uma endoscopia hoje, amanhã estou de volta", "OUT1"))
    post(incoming("Melhoras!", "IN2"))

    assert Customer.objects.count() == 1
    assert ConversationModel.objects.count() == 1
    conversation = ConversationModel.objects.get()
    texts = [m.content for m in MessageModel.objects(conversation=conversation, direction__ne="INTERNAL").order_by("created_at")]
    assert texts[0] == "Amiga, o que aconteceu com você?"
    assert texts[-2:] == ["Fiz uma endoscopia hoje, amanhã estou de volta", "Melhoras!"]
    assert conversation.tag == "OPERADOR"


@pytest.mark.django_db
def test_lid_is_learned_from_old_incoming_messages():
    post(incoming("Oi", "IN1"))
    Customer.objects.update(unset__whatsapp_lid=True)  # contato de antes do campo

    post(from_phone("Oi, tudo bem?", "OUT1"))

    assert Customer.objects.count() == 1
    assert Customer.objects.get().whatsapp_lid == LID


@pytest.mark.django_db
def test_contact_first_seen_from_phone_gets_the_number_when_customer_writes():
    post(from_phone("Oi Gleidson, aqui é a Erica", "OUT1"))
    assert Customer.objects.get().phone == LID

    post(incoming("Oi Erica!", "IN1"))

    customer = Customer.objects.get()
    assert (customer.phone, customer.whatsapp_lid) == (PHONE, LID)
    assert ConversationModel.objects.count() == 1


@pytest.mark.django_db
def test_waiting_message_reaction_and_call_do_not_become_messages(ai_task):
    post(incoming("Oi", "IN1"))
    before = MessageModel.objects.count()

    post(incoming(message_id="W1", waitingMessage=True))
    post(incoming(message_id="R1", reaction={"value": "👍", "referencedMessage": {"messageId": "IN1"}}))
    post(incoming(message_id="C1", notification="CALL_MISSED_VOICE"))

    assert MessageModel.objects.count() == before
    assert not MessageModel.objects(content=PLACEHOLDER)

    # A mensagem decifrada chega depois com o mesmo messageId do "aguardando mensagem" e entra.
    post(incoming("Consegue me mandar o orçamento?", "W1"))
    assert MessageModel.objects(external_id="W1").get().content == "Consegue me mandar o orçamento?"


@pytest.mark.django_db
def test_location_from_customer_is_labelled():
    post(incoming("Oi", "IN1"))
    post(incoming(message_id="L1", location={"latitude": -16.6, "longitude": -49.2, "name": "Salão Ipê"}))
    assert MessageModel.objects(external_id="L1").get().content == "[Localização] Salão Ipê"


def _split_contacts():
    """Como ficou em produção antes da correção: contato com número e contato @lid separados."""
    from chat.repositories.conversation_repository import ConversationRepository
    real = Customer(name="Gleidson", phone=PHONE).save()
    lid_customer = Customer(name="Gleidson", phone=LID).save()
    real_conv = ConversationRepository.create_conversation(str(real.id))
    lid_conv = ConversationRepository.create_conversation(str(lid_customer.id))
    MessageModel(conversation=real_conv, customer=real, direction="INCOMING", role="user", content="Amiga, tudo bem?",
                 raw_metadata=incoming("Amiga, tudo bem?")).save()
    MessageModel(conversation=lid_conv, customer=lid_customer, direction="OUTGOING", role="OPERATOR",
                 content="Fiz uma endoscopia", raw_metadata={"sent_from_phone": True}).save()
    MessageModel(conversation=real_conv, customer=real, direction="INCOMING", role="user", content=PLACEHOLDER,
                 raw_metadata={"phone": PHONE, "waitingMessage": True}).save()
    # Áudio do cliente cuja transcrição falhou: virou o mesmo texto, mas é mensagem de verdade.
    MessageModel(conversation=real_conv, customer=real, direction="INCOMING", role="user", content=PLACEHOLDER,
                 raw_metadata={"phone": PHONE, "audio": {"audioUrl": "https://cdn.z-api.io/a.ogg"}},
                 external_id="AUDIO1").save()
    return real, lid_customer, real_conv


@pytest.mark.django_db
def test_fix_command_dry_run_changes_nothing():
    _split_contacts()
    out = StringIO()
    call_command("fix_whatsapp_contacts", stdout=out)
    assert "1 contato(s) @lid juntado(s), 0 para revisar à mão; 'Olá, Tenho interesse': 1 com rótulo corrigido, 1 aviso(s) apagado(s)" in out.getvalue()
    assert Customer.objects.count() == 2
    assert MessageModel.objects(content=PLACEHOLDER).count() == 2


@pytest.mark.django_db
def test_fix_command_merges_lid_contact_and_removes_placeholders():
    real, lid_customer, real_conv = _split_contacts()
    old_ad_click = MessageModel(conversation=real_conv, customer=real, direction="INCOMING", role="user",
                                content=PLACEHOLDER, raw_metadata=incoming(PLACEHOLDER)).save()

    call_command("fix_whatsapp_contacts", "--apply", stdout=StringIO())

    assert list(Customer.objects.scalar("phone")) == [PHONE]
    assert Customer.objects.get().whatsapp_lid == LID
    assert ConversationModel.objects.count() == 1
    contents = [m.content for m in MessageModel.objects(conversation=real_conv, direction__ne="INTERNAL")]
    assert "Fiz uma endoscopia" in contents
    # Some só o aviso vazio; o que o cliente digitou de verdade (tem text no payload) fica.
    assert [m.id for m in MessageModel.objects(content=PLACEHOLDER)] == [old_ad_click.id]
    audio = MessageModel.objects(external_id="AUDIO1").get()
    assert (audio.content, audio.message_type, audio.media_url) == ("[Áudio]", "audio", "https://cdn.z-api.io/a.ogg")
    real_conv.reload()
    assert real_conv.tag == "OPERADOR"


@pytest.mark.django_db
def test_conversation_list_survives_a_deleted_quote(api_client):
    """Orçamento apagado com a conversa ainda apontando para ele: a lista não pode dar 500."""
    from crm.models.quote_model import Quote
    post(incoming("Oi", "IN1"))
    conversation = ConversationModel.objects.get()
    quote = Quote(customer=conversation.customer).save()
    ConversationModel.objects(id=conversation.id).update(set__quote=quote)
    Quote._get_collection().delete_one({"_id": quote.id})  # some sem o NULLIFY, como em produção

    resp = api_client.get("/api/v1/chat/conversations/?page_size=20&status=OPEN")
    assert resp.status_code == 200, resp.data
    assert resp.data["results"][0]["quote_id"] is None

    # A mensagem seguinte do cliente continua entrando e a conversa fica sem a referência quebrada.
    post(incoming("Ainda está aí?", "IN2"))
    assert MessageModel.objects(external_id="IN2").count() == 1
    assert ConversationModel._get_collection().find_one({"_id": conversation.id}).get("quote") != quote.id


@pytest.mark.django_db
def test_fix_command_keeps_lid_contact_with_lead_data_for_review():
    from datetime import datetime
    real, lid_customer, _ = _split_contacts()
    Customer.objects(id=lid_customer.id).update(set__funnel_entered_at=datetime.utcnow())
    out = StringIO()

    call_command("fix_whatsapp_contacts", "--apply", stdout=out)

    assert "revisar à mão (está no funil ou foi qualificado pela IA)" in out.getvalue()
    assert Customer.objects.count() == 2


@pytest.mark.django_db
def test_business_messages_and_videos_get_a_label():
    post(incoming("Oi", "IN1"))
    post(incoming(message_id="B1", buttonsMessage={"message": "Promoção de caixas de som", "buttons": []}))
    post(incoming(message_id="H1", hydratedTemplate={"header": {}, "message": "", "hydratedButtons": []}))
    assert MessageModel.objects(external_id="B1").get().content == "[Mensagem interativa] Promoção de caixas de som"
    assert MessageModel.objects(external_id="H1").get().content == "[Mensagem interativa]"
