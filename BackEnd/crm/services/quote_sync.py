"""Espelha os dados do evento da cotação ativa no `Customer`.

Em produção a IA grava o evento na coleção `quotes` (Quote). O funil, a calculadora e o dashboard
da SDR leem esses campos no `Customer` (lead atual). Este espelho mantém os dois lados iguais sem
migrar nem apagar nada no banco: só copia valores preenchidos, nunca zera um campo do lead.
"""
from datetime import datetime

from utils.logger import logger

MIRRORED_FIELDS = (
    "celebration_type", "event_title", "event_date", "guest_count", "quoted_amount",
    "contract_value", "venue", "notes", "proposal_sent_at", "last_interaction_at", "next_step",
)


def sync_customer_from_quote(quote) -> None:
    try:
        from crm.models.custumer_model import Customer
        customer_id = quote.customer_ref_id()
        if not customer_id:
            return
        updates = {}
        for field in MIRRORED_FIELDS:
            value = getattr(quote, field, None)
            if value in (None, "", 0, 0.0):
                continue
            updates[f"set__{field}"] = value
        if not updates:
            return
        updates["set__updated_at"] = datetime.utcnow()
        Customer.objects(id=customer_id).update_one(**updates)
    except Exception as e:  # o espelho nunca pode derrubar o fluxo da IA
        logger.error(f"[QuoteSync] Falha ao espelhar cotação no lead: {e}")
