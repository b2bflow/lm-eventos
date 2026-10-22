"""W3: relatório de contatos que mandaram mensagem e ficaram sem resposta."""
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm.models.custumer_model import Customer


def _chat(name, phone, *messages, human_operator=False):
    """messages: (minutos atrás, direção, papel)."""
    customer = Customer(name=name, phone=phone, human_operator=human_operator).save()
    conversation = ConversationModel(customer=customer, tag="AGENTE").save()
    for minutes, direction, role in messages:
        MessageModel(conversation=conversation, customer=customer, direction=direction, role=role, content="oi",
                     created_at=datetime.utcnow() - timedelta(minutes=minutes)).save()
    return customer


@pytest.mark.django_db
def test_lists_unanswered_and_lid_contacts():
    _chat("Sem resposta", "5562900000101", (30, "INCOMING", "user"))
    _chat("Respondido", "5562900000102", (30, "INCOMING", "user"), (29, "OUTGOING", "assistant"))
    _chat("Lid", "123456789012345@lid", (30, "INCOMING", "user"), (29, "OUTGOING", "assistant"))
    _chat("Agora", "5562900000104", (2, "INCOMING", "user"))
    _chat("Parceiro", "5562900000105", (30, "INCOMING", "user"), human_operator=True)
    _chat("Antigo", "5562900000106", (60 * 24 * 30, "INCOMING", "user"))

    out = StringIO()
    call_command("unanswered_contacts", "--csv", stdout=out)
    lines = out.getvalue().strip().splitlines()
    assert lines[0].startswith("situacao,nome,telefone")
    found = {line.split(",")[1]: line.split(",")[0] for line in lines[1:]}
    assert found == {"Sem resposta": "sem resposta", "Lid": "@lid"}

    out = StringIO()
    call_command("unanswered_contacts", stdout=out)
    assert "2 contato(s)" in out.getvalue()
