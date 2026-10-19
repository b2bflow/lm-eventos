from datetime import datetime

from mongoengine import (
    BooleanField, DateTimeField, DictField, Document, FloatField, IntField, ListField, ReferenceField, StringField,
)

from crm.models.custumer_model import Customer

MODES = ("porta", "corporativo", "social", "produto_unico")
STATUSES = ("rascunho", "aguardando_aprovacao", "aprovada", "enviada", "aceita", "recusada", "vencida", "substituida")

STATUS_LABELS = {
    "rascunho": "Rascunho",
    "aguardando_aprovacao": "Aguardando aprovação",
    "aprovada": "Aprovada",
    "enviada": "Enviada",
    "aceita": "Aceita",
    "recusada": "Recusada",
    "vencida": "Vencida",
    "substituida": "Substituída por nova versão",
}


class Proposal(Document):
    """Proposta comercial. Cada edição salva uma nova versão; a anterior fica `substituida`."""

    meta = {
        'collection': 'proposals',
        'strict': False,
        'indexes': ['customer', 'status', '-created_at', ('customer', '-version'), 'valid_until'],
    }

    customer = ReferenceField(Customer, required=True, reverse_delete_rule=2)
    opportunity_id = StringField(null=True)  # lead arquivado do contato; vazio = lead atual
    version = IntField(required=True, default=1)
    author_id = StringField(null=True)
    mode = StringField(choices=MODES, required=True)
    inputs = DictField()  # snapshot das entradas
    lines = ListField(DictField())
    costs = ListField(DictField())
    items_total = FloatField(default=0)
    costs_total = FloatField(default=0)
    margin_pct = FloatField(default=0)
    with_invoice = BooleanField(default=False)
    invoice_value = FloatField(default=0)
    discount = FloatField(default=0)
    manual_adjustment = FloatField(default=0)
    total = FloatField(default=0)
    periods = IntField(default=1)
    status = StringField(choices=STATUSES, default="rascunho")
    lock_reasons = ListField(DictField())
    warnings = ListField(StringField())
    requires_technical_visit = BooleanField(default=False)
    requires_meeting = BooleanField(default=False)  # social fora do padrão: reunião com a Erica
    period_start = DateTimeField(null=True)
    period_end = DateTimeField(null=True)
    valid_until = DateTimeField(null=True)
    pdf_url = StringField(null=True)
    sent_at = DateTimeField(null=True)
    accepted_at = DateTimeField(null=True)
    approval = DictField()  # {requested_at, decided_at, decided_by, decision, note}
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        def iso(v):
            return v.isoformat() if v else None
        approval = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in (self.approval or {}).items()}
        return {
            "id": str(self.id), "customer_id": str(self.customer.id) if self.customer else None,
            "customer_name": getattr(self.customer, "name", None), "version": self.version,
            "opportunity_id": self.opportunity_id,
            "author_id": self.author_id, "mode": self.mode, "inputs": dict(self.inputs or {}),
            "lines": list(self.lines or []), "costs": list(self.costs or []),
            "items_total": self.items_total, "costs_total": self.costs_total, "margin_pct": self.margin_pct,
            "with_invoice": self.with_invoice, "invoice_value": self.invoice_value, "discount": self.discount,
            "manual_adjustment": self.manual_adjustment, "total": self.total, "periods": self.periods,
            "status": self.status, "status_label": STATUS_LABELS.get(self.status, self.status),
            "lock_reasons": list(self.lock_reasons or []), "warnings": list(self.warnings or []),
            "requires_technical_visit": self.requires_technical_visit,
            "requires_meeting": bool(self.requires_meeting),
            "period_start": iso(self.period_start), "period_end": iso(self.period_end),
            "valid_until": iso(self.valid_until), "pdf_url": self.pdf_url, "sent_at": iso(self.sent_at),
            "accepted_at": iso(self.accepted_at), "approval": approval,
            "created_at": iso(self.created_at), "updated_at": iso(self.updated_at),
        }
