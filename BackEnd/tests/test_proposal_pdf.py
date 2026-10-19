"""PDF da proposta e envio pelo WhatsApp em um clique."""
import base64
from datetime import datetime

import pytest

from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel
from crm import domain
from crm.models.custumer_model import Customer
from crm.models.lm_settings_model import LmSettings
from crm.models.log_service_model import ServiceLog
from sales.catalog import SOCIAL_BASIC_PACKAGE, merge_price_table
from sales.services.proposal_pdf import build_pdf_context, file_name, render_pdf
from sales.services.quote_calculator import SocialInput, calculate_social

SETTINGS = {"proposal_validity_days": 5, "payment_terms_text": "Forma de pagamento: PIX.",
            "down_payment_text": "Sinal de 50% na assinatura.", "cancellation_text": "Cancelamento: ver contrato."}


def social_proposal(**overrides):
    result = calculate_social(SocialInput(guests=150, **SOCIAL_BASIC_PACKAGE), merge_price_table(None)).to_dict()
    proposal = {"mode": "social", "version": 1, "inputs": {"event_date": "2026-11-21", "guests": 150, "structure": "gol_3x4"},
                "lines": result["lines"], "costs": result["operational"], "total": 12680, "with_invoice": True}
    proposal.update(overrides)
    return proposal


def test_context_formats_value_blocks_and_conditions():
    ctx = build_pdf_context(social_proposal(), {"name": "Ana", "venue": "JL Eventos"}, SETTINGS,
                            valid_until=datetime(2026, 10, 21), issued_at=datetime(2026, 10, 16))
    assert ctx["total"] == "R$ 12.680,00"
    titles = [b["title"] for b in ctx["blocks"]]
    assert titles == ["Estrutura", "Som", "Iluminação", "Vídeo", "Equipe"]
    assert ctx["blocks"][0]["items"] == ["01 Gol 3x4 m (Q30)"]  # o kit aparece montado, não peça a peça
    assert "08 Par LED" in ctx["blocks"][2]["items"]
    assert "06 m² Painel de LED (social, técnico incluso)" in ctx["blocks"][3]["items"]
    assert ctx["blocks"][-1]["items"] == ["Montagem e desmontagem", "DJ"]
    assert "Forração" in ctx["not_included"] and "Projeto" in ctx["not_included"]
    assert "Deslocamento fora de Goiânia" in ctx["not_included"]
    assert "Transporte, carga e descarga em Goiânia" in ctx["included"] and "Nota fiscal" in ctx["included"]
    assert ctx["payment"] == ["Forma de pagamento: PIX.", "Sinal de 50% na assinatura."]
    assert ctx["validity"] == "Esta proposta tem validade de 05 (cinco) dias, até 21/10/2026."
    assert ctx["header"][:2] == ["Data do evento: 21/11/2026", "Local: JL Eventos"]
    assert ctx["issued_at"] == "16 de outubro de 2026"


def test_context_porta_and_single_product():
    porta = build_pdf_context({"mode": "porta", "inputs": {"pickup_date": "2026-10-23", "return_date": "2026-10-26"},
                               "lines": [{"code": "q30_torre_5m", "name": "Torre Q30 5 m", "block": "estrutura",
                                          "qty": 4, "unit": "peça"}], "costs": [], "total": 300},
                              {"name": "Lucas"}, SETTINGS)
    assert porta["header"][:2] == ["Retirada: 23/10/2026", "Devolução: 26/10/2026"]
    assert porta["blocks"] == [{"title": "Estrutura", "items": ["04 Torre Q30 5 m"]}]
    assert "Montagem e desmontagem" in porta["not_included"]
    single = build_pdf_context({"mode": "produto_unico", "inputs": {"event_date": "2026-11-21", "delivery": "entrega"},
                                "lines": [], "costs": [{"code": "entrega_praticavel", "subtotal": 150}], "total": 750},
                               {"name": "Bia"}, SETTINGS)
    assert "Entrega no local" in single["header"] and "Entrega e retirada no local" in single["included"]


def test_render_pdf_has_cover_static_pages_and_value():
    ctx = build_pdf_context(social_proposal(), {"name": "Ana Paula"}, SETTINGS, valid_until=datetime(2026, 10, 21))
    data = render_pdf(ctx, compress=False)
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 5  # capa, missão, referências, evento, contato
    assert b"R$ 12.680,00" in data and b"PROPOSTA" in data
    assert file_name(ctx) == "Proposta_LM_Ana_Paula_v1.pdf"


# --- API -------------------------------------------------------------------------------------

@pytest.fixture
def lead_with_chat():
    customer = Customer(name="Ana", phone="5562988887777", customer_state_now=domain.QUALIFIED, product="social").save()
    conversation = ConversationModel(customer=customer).save()
    return customer, conversation


def _save_social(client, customer):
    inputs = {"event_date": "2026-11-21", "guests": 100, "dance_floor": False, "margin": 0.2, "with_invoice": False}
    resp = client.post("/api/v1/sales/proposals/", {"customer_id": str(customer.id), "mode": "social", "inputs": inputs},
                       format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


@pytest.mark.django_db
def test_send_whatsapp_sends_pdf_moves_card_and_records_timeline(api_client, lead_with_chat, zapi_outbox):
    customer, conversation = lead_with_chat
    proposal = _save_social(api_client, customer)
    resp = api_client.post(f"/api/v1/sales/proposals/{proposal['id']}/send-whatsapp/")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "enviada" and "/pdf/Proposta_LM_Ana_v1.pdf?t=" in resp.data["pdf_url"]

    doc = [m for m in zapi_outbox if "document" in m][0]
    assert doc["phone"] == customer.phone and doc["file_name"].endswith(".pdf")
    assert base64.b64decode(doc["document"].split(",", 1)[1]).startswith(b"%PDF")
    assert "R$ 1.560,00" in doc["caption"]

    customer.reload()
    assert customer.customer_state_now == domain.PROPOSAL_SENT and customer.quoted_amount == 1560.0
    log = ServiceLog.objects(customer=customer, action_type="PROPOSAL_SENT").first()
    assert "WhatsApp" in log.description
    message = MessageModel.objects(conversation=conversation, message_type="file").first()
    assert message.direction == "OUTGOING" and message.media_url == resp.data["pdf_url"]


@pytest.mark.django_db
def test_send_whatsapp_failure_keeps_proposal_unsent(api_client, lead_with_chat, monkeypatch):
    from gateway.adapters.zapi_adapter import ZAPIClient
    customer, _ = lead_with_chat
    proposal = _save_social(api_client, customer)

    def boom(self, **kwargs):
        raise ConnectionError("Z-API fora do ar")

    monkeypatch.setattr(ZAPIClient, "send_document", boom)
    resp = api_client.post(f"/api/v1/sales/proposals/{proposal['id']}/send-whatsapp/")
    assert resp.status_code == 400 and "WhatsApp" in resp.data["detail"]
    customer.reload()
    assert customer.customer_state_now == domain.QUALIFIED


@pytest.mark.django_db
def test_pdf_endpoint_requires_login_or_signed_link(api_client, lead_with_chat):
    from rest_framework.test import APIClient
    from sales.services.proposal_service import signed_pdf_url
    customer, _ = lead_with_chat
    proposal = _save_social(api_client, customer)
    url = f"/api/v1/sales/proposals/{proposal['id']}/pdf/"

    resp = api_client.get(url)
    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    anonymous = APIClient()
    assert anonymous.get(url).status_code == 401
    assert anonymous.get(url, {"t": "forjado"}).status_code == 401
    assert anonymous.get(signed_pdf_url(proposal["id"])).status_code == 200


@pytest.mark.django_db
def test_pdf_uses_configurable_payment_texts(api_client, lead_with_chat):
    cfg = LmSettings.get()
    cfg.payment_terms_text = "Pagamento em duas vezes."
    cfg.save()
    from sales.services.proposal_service import ProposalService, _proposal
    customer, _ = lead_with_chat
    proposal = _proposal(_save_social(api_client, customer)["id"])
    ctx = build_pdf_context(proposal.to_dict(), customer.to_dict(), LmSettings.get().to_dict())
    assert ctx["payment"][0] == "Pagamento em duas vezes." and ctx["payment"][1] == "Sinal: a combinar."
    content, name = ProposalService().pdf(str(proposal.id))
    assert content.startswith(b"%PDF") and name.startswith("Proposta_LM_Ana")
