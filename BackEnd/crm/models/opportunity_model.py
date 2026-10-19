from datetime import datetime

from mongoengine import (
    BooleanField, DateTimeField, DictField, Document, FloatField, IntField, ListField, ReferenceField, StringField,
)

from crm import domain
from crm.models.custumer_model import Customer, _iso

# Campos do lead copiados do Customer quando o lead é arquivado.
LEAD_FIELDS = (
    'product', 'lost_reason', 'qualification', 'pending_fields', 'attachments', 'flags', 'quoted_amount',
    'contract_value', 'event_date', 'event_title', 'celebration_type', 'guest_count', 'venue', 'owner',
    'needs_erica', 'qualified_at', 'first_contact_at', 'proposal_sent_at', 'next_step',
)


class Opportunity(Document):
    """Lead encerrado de um contato (coleção `opportunities`).

    O lead em andamento continua no próprio Customer (é ele que conversa, funil, propostas,
    tarefas, agenda e a IA usam). Quando um contato com lead encerrado (contrato assinado ou
    perdido) começa um lead novo, o lead anterior é copiado para cá e as propostas e a linha do
    tempo dele passam a apontar para esta oportunidade (`opportunity_id`).
    """

    meta = {
        'collection': 'opportunities',
        'strict': False,
        'indexes': ['customer', ('customer', '-number'), 'stage', '-started_at'],
    }

    customer = ReferenceField(Customer, required=True, reverse_delete_rule=2)  # o contato
    number = IntField(default=1)  # 1º, 2º, 3º lead do contato
    stage = StringField(choices=domain.STAGES, required=True)

    product = StringField(null=True)
    lost_reason = StringField(null=True)
    qualification = DictField()
    pending_fields = ListField(StringField())
    attachments = ListField(DictField())
    flags = ListField(StringField())
    quoted_amount = FloatField(default=0)
    contract_value = FloatField(default=0)
    event_date = DateTimeField(null=True)
    event_title = StringField(null=True)
    celebration_type = StringField(null=True)
    guest_count = IntField(default=0)
    venue = StringField(null=True)
    owner = StringField(null=True)
    needs_erica = BooleanField(default=False)
    qualified_at = DateTimeField(null=True)
    first_contact_at = DateTimeField(null=True)
    proposal_sent_at = DateTimeField(null=True)
    next_step = StringField(null=True)

    started_at = DateTimeField(null=True)
    closed_at = DateTimeField(null=True)
    archived_at = DateTimeField(default=datetime.utcnow)
    archived_by = StringField(null=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "customer_id": str(self.customer.id) if self.customer else None,
            "number": self.number,
            "current": False,
            "stage": self.stage,
            "product": self.product,
            "lost_reason": self.lost_reason,
            "qualification": dict(self.qualification or {}),
            "pending_fields": list(self.pending_fields or []),
            "attachments": [
                {**a, "received_at": _iso(a.get("received_at")) if isinstance(a.get("received_at"), datetime) else a.get("received_at")}
                for a in (self.attachments or [])
            ],
            "flags": list(self.flags or []),
            "quoted_amount": self.quoted_amount or 0,
            "contract_value": self.contract_value or 0,
            "event_date": _iso(self.event_date),
            "event_title": self.event_title,
            "celebration_type": self.celebration_type,
            "guest_count": self.guest_count or 0,
            "venue": self.venue,
            "owner": self.owner,
            "qualified_at": _iso(self.qualified_at),
            "proposal_sent_at": _iso(self.proposal_sent_at),
            "started_at": _iso(self.started_at),
            "closed_at": _iso(self.closed_at),
        }

    def to_lead_row(self) -> dict:
        """Mesmo formato de linha que o dashboard lê do Customer (lead histórico)."""
        return {
            "created_at": self.started_at or self.archived_at,
            "customer_state_now": self.stage,
            "proposal_sent_at": self.proposal_sent_at,
            "quoted_amount": self.quoted_amount,
            "contract_value": self.contract_value,
            "event_date": self.event_date,
        }
