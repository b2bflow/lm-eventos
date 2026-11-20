"""Quem aparece no funil.

O funil foi "zerado" para o início do atendimento pela plataforma: os leads antigos continuam no
banco (e na página Contatos), mas o quadro, a fila da SDR e as regras automáticas só olham para
quem tem `Customer.funnel_entered_at`. Um contato entra no funil quando:

- o cliente clica em "Solicitar orçamento" no menu da IA (`chat.services.message_service`): entra na
  coluna "Pediu orçamento", mesmo que pare de responder antes do fim da qualificação (reunião com o
  Marcelo, 19/11: o lead de tráfego pago que some no meio não pode se perder);
- a IA termina a qualificação, cotação em WAITING_BUDGET (`crm.services.quote_service`): entra como
  "Lead qualificado" (ou sai de "Pediu orçamento" para lá). Conversa nova sozinha não entra;
- alguém abre um lead à mão (Novo lead no funil, Converter em lead no WhatsApp, Abrir lead em Contatos);
- alguém salva uma proposta para o contato na calculadora (`sales.services.proposal_service`).

As funções nunca levantam erro: entrar no funil não pode derrubar o fluxo da mensagem.
"""
from datetime import datetime

from utils.logger import logger

# Contatos que nunca entram sozinhos (parceiro, fornecedor, candidato ficam com a Erica)
_OUT_OF_FUNNEL_TYPES = ("parceiro", "fornecedor", "candidato")


def _customer_id(customer) -> str | None:
    if customer is None:
        return None
    if isinstance(customer, dict):
        return str(customer.get("id") or "") or None
    return str(getattr(customer, "id", customer) or "") or None


def enter_funnel(customer, now: datetime | None = None, only_eligible: bool = False) -> bool:
    """Marca a entrada no funil (só a primeira vez). Devolve True quando marcou agora.

    only_eligible: para as entradas automáticas, não marca parceiro, fornecedor, candidato nem
    contato com operador humano.
    """
    from crm.models.custumer_model import Customer
    try:
        customer_id = _customer_id(customer)
        if not customer_id:
            return False
        query = Customer.objects(id=customer_id, funnel_entered_at=None)
        if only_eligible:
            query = query.filter(human_operator__ne=True, contact_type__nin=list(_OUT_OF_FUNNEL_TYPES))
        return bool(query.update_one(set__funnel_entered_at=now or datetime.utcnow()))
    except Exception as e:
        logger.error(f"[FunnelEntry] Falha ao colocar o contato no funil: {e}")
        return False


def mark_quote_requested(customer, now: datetime | None = None, reopen: bool = True) -> str | None:
    """O cliente clicou em "Solicitar orçamento" no menu da IA: grava a data (só a primeira do lead) e
    coloca o lead no funil. Lead novo fica na coluna "Pediu orçamento" (etapa NEW_LEAD); lead que já
    anda no funil não muda de etapa.

    Lead encerrado (contrato assinado ou perdido) ou de antes do funil zerado vai para o histórico do
    contato e começa um lead novo, como no "Abrir lead". `reopen=False` (backfill) não mexe nesses:
    devolve "skipped".

    Devolve "entered" (entrou no funil agora), "marked" (já estava no funil), "skipped" ou None
    (contato fora do funil por regra: parceiro, fornecedor, candidato, grupo, ou erro).
    """
    from crm import domain
    from crm.models.custumer_model import Customer
    try:
        customer_id = _customer_id(customer)
        doc = Customer.objects(id=customer_id).first() if customer_id else None
        if (doc is None or doc.human_operator or getattr(doc, "whatsapp_group", False)
                or (doc.contact_type or "lead") in _OUT_OF_FUNNEL_TYPES):
            return None
        now = now or datetime.utcnow()
        closed = doc.stage in (domain.CONTRACT_SIGNED, domain.LOST)
        stale = doc.funnel_entered_at is None and bool(doc.product or doc.stage != domain.NEW_LEAD)
        if closed or stale:
            if not reopen:
                return "skipped"
            from crm.services.contact_service import ContactService
            ContactService().archive_current_lead(doc, now=now)
            doc.reload()

        # updated_at = agora (o card sobe na coluna), mesmo no backfill, que passa a hora do clique em `now`.
        first_time = bool(Customer.objects(id=customer_id, quote_requested_at=None).update_one(
            set__quote_requested_at=now, set__updated_at=datetime.utcnow()))
        entered = enter_funnel(customer_id, now=now, only_eligible=True)
        if first_time:
            from crm.repositories.log_service_repository import ServiceLogRepository
            ServiceLogRepository.create_log(
                customer=doc, operator_id=None, action_type="QUOTE_REQUESTED",
                description="Cliente clicou em \"Solicitar orçamento\" no WhatsApp."
                            + (" Entrou no funil em \"Pediu orçamento\"." if entered and doc.stage == domain.NEW_LEAD else ""),
            )
        return "entered" if entered else "marked"
    except Exception as e:
        logger.error(f"[FunnelEntry] Falha ao marcar pedido de orçamento: {e}")
        return None


def mark_ai_qualified(customer, now: datetime | None = None) -> None:
    """A IA terminou a qualificação: grava a data (só a primeira do lead), garante o lead no funil e
    leva o card para "Lead qualificado" (lead que já está mais adiante não volta de etapa)."""
    from crm import domain
    from crm.models.custumer_model import Customer
    try:
        customer_id = _customer_id(customer)
        if not customer_id:
            return
        now = now or datetime.utcnow()
        first_time = bool(Customer.objects(id=customer_id, ai_qualified_at=None).update_one(set__ai_qualified_at=now))
        enter_funnel(customer_id, now=now, only_eligible=True)
        doc = Customer.objects(id=customer_id).first()
        if doc and doc.funnel_entered_at and (doc.stage == domain.NEW_LEAD or doc.customer_state_now not in domain.STAGES):
            from crm.container import CrmContainer
            target = domain.QUALIFIED if doc.stage == domain.NEW_LEAD else doc.stage
            CrmContainer.get_pipeline_service().change_stage(customer_id, target, system=True,
                                                             note="Qualificado pela IA.")
        if first_time and doc:
            _notify_group(customer_id)
    except Exception as e:
        logger.error(f"[FunnelEntry] Falha ao marcar lead qualificado pela IA: {e}")


def _notify_group(customer_id: str) -> None:
    """Avisa o grupo de atendimento em segundo plano: o envio pela Z-API não atrasa a resposta da IA."""
    from threading import Thread

    def send():
        try:
            from crm.container import CrmContainer
            from crm.models.custumer_model import Customer
            doc = Customer.objects(id=customer_id).first()
            if doc:
                CrmContainer.get_notification_service().notify_ai_lead(doc)
        except Exception as e:
            logger.error(f"[FunnelEntry] Falha ao avisar o grupo de atendimento: {e}")

    Thread(target=send, daemon=True).start()
