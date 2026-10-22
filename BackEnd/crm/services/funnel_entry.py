"""Quem aparece no funil.

O funil foi "zerado" para o início do atendimento pela plataforma: os leads antigos continuam no
banco (e na página Contatos), mas o quadro, a fila da SDR e as regras automáticas só olham para
quem tem `Customer.funnel_entered_at`. Um contato entra no funil quando:

- começa uma conversa nova atendida pela IA (`chat.repositories.conversation_repository`);
- a IA termina a qualificação, cotação em WAITING_BUDGET (`crm.services.quote_service`);
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
    """A IA terminou a qualificação: grava a data (só a primeira do lead) e garante o lead no funil."""
    from crm.models.custumer_model import Customer
    try:
        customer_id = _customer_id(customer)
        if not customer_id:
            return
        now = now or datetime.utcnow()
        Customer.objects(id=customer_id, ai_qualified_at=None).update_one(set__ai_qualified_at=now)
        enter_funnel(customer_id, now=now, only_eligible=True)
    except Exception as e:
        logger.error(f"[FunnelEntry] Falha ao marcar lead qualificado pela IA: {e}")
