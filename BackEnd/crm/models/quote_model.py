from datetime import datetime
from mongoengine import (
    CASCADE,
    DateTimeField,
    Document,
    FloatField,
    IntField,
    ReferenceField,
    StringField,
)
from mongoengine.errors import DoesNotExist
from crm.models.custumer_model import Customer


class Quote(Document):
    meta = {
        "collection": "quotes",
        "indexes": ["customer", "status", "-created_at", "-updated_at"],
        "strict": False,
    }

    customer = ReferenceField(Customer, required=True, reverse_delete_rule=CASCADE)

    STATUS_CHOICES = (
        ("ANALYSIS", "Analise"),
        ("WAITING_BUDGET", "Aguardando Orcamento"),
        ("BUDGET", "Orcamento"),
        ("NEGOTIATING", "Negociando"),
        ("WON", "Venda"),
        ("LOST", "Perdido"),
    )
    status = StringField(choices=STATUS_CHOICES, default="ANALYSIS")

    celebration_type = StringField(max_length=80, null=True)
    event_title = StringField(max_length=140, null=True)
    event_date = DateTimeField(null=True)
    event_time = StringField(max_length=5, null=True)
    guest_count = IntField(default=0)
    quoted_amount = FloatField(default=0)
    contract_value = FloatField(default=0)
    venue = StringField(max_length=160, null=True)
    notes = StringField(null=True)
    operator_requests = StringField(null=True)
    proposal_sent_at = DateTimeField(null=True)
    last_interaction_at = DateTimeField(null=True)
    next_step = StringField(max_length=160, null=True)
    closed_at = DateTimeField(null=True)

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def has_valid_customer(self) -> bool:
        try:
            return self.customer is not None
        except DoesNotExist:
            return False

    def customer_ref_id(self):
        # Lê o id bruto da referência sem disparar consulta ao banco
        ref = self._data.get("customer")
        return getattr(ref, "id", None)

    def to_dict(self, customer: Customer | None = None) -> dict:
        if customer is None:
            customer = self.customer if self.has_valid_customer() else None
        return {
            "id": str(self.id),
            "quote_id": str(self.id),
            "customer": str(customer.id) if customer else None,
            "customer_id": str(customer.id) if customer else None,
            "name": getattr(customer, "name", None),
            "phone": getattr(customer, "phone", None),
            "customer_state_now": self.status,
            "actual_status": self.status,
            "status": self.status,
            "customer_custom_tag": getattr(customer, "customer_custom_tag", None),
            "celebration_type": self.celebration_type,
            "event_title": self.event_title,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "event_time": self.event_time,
            "guest_count": self.guest_count,
            "quoted_amount": self.quoted_amount or 0,
            "contract_value": self.contract_value or 0,
            "venue": self.venue,
            "notes": self.notes,
            "operator_requests": self.operator_requests,
            "proposal_sent_at": self.proposal_sent_at.isoformat() if self.proposal_sent_at else None,
            "last_interaction_at": self.last_interaction_at.isoformat() if self.last_interaction_at else None,
            "next_step": self.next_step,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
