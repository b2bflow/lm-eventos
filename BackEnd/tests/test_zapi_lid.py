"""Contatos que a Z-API identifica por `@lid` (sem o número): a resposta da IA tem que sair.

Antes, send_message tirava o "@lid", sobrava um número de 14-15 dígitos e o envio era recusado
como "telefone inválido": o cliente recebia o menu (enviado sem essa validação), mas nunca a
resposta da IA.
"""
from unittest.mock import MagicMock, patch

from gateway.adapters.zapi_adapter import ZAPIClient

# Guardado na importação: o conftest troca send_message por um falso durante os testes.
REAL_SEND_MESSAGE = ZAPIClient.send_message
LID = "203740298143829@lid"


def test_lid_is_recognized():
    assert ZAPIClient.is_lid(LID)
    assert not ZAPIClient.is_lid("5562999990000")
    assert not ZAPIClient.is_lid("abc@lid")


def test_lid_passes_validation_and_keeps_its_suffix():
    client = ZAPIClient()
    assert client._ZAPIClient__validate_cell_number(LID)
    assert client._resolve_phone(LID) == LID
    assert client.get_phone(phone=LID) == LID
    assert not client._ZAPIClient__validate_cell_number("2037402981438290")  # número comprido continua inválido


def test_ai_reply_is_sent_to_lid_contact():
    response = MagicMock()
    response.json.return_value = {"zaapId": "x"}
    with patch("gateway.adapters.zapi_adapter.requests.post", return_value=response) as post, \
            patch("gateway.adapters.zapi_adapter.time.sleep"):
        assert REAL_SEND_MESSAGE(ZAPIClient(), LID, "Oi! Me conta sobre o seu evento?") is True
    assert post.call_args.kwargs["json"]["phone"] == LID
