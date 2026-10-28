"""Quem aparece no funil.

O funil foi "zerado" para o início do atendimento pela plataforma: os leads antigos continuam no
banco (e na página Contatos), mas o quadro, a fila da SDR e as regras automáticas só olham para
quem tem `Customer.funnel_entered_at`. Um contato entra no funil quando:

- a IA termina a qualificação, cotação em WAITING_BUDGET (`crm.services.quote_service`): entra como
  "Lead qualificado". Conversa nova sozinha não entra (só os qualificados pela IA, pedido do Marcelo);
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
