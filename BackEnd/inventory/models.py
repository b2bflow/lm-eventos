from datetime import datetime

from bson import ObjectId
from mongoengine import (
    NULLIFY, BooleanField, DateTimeField, Document, EmbeddedDocument, EmbeddedDocumentListField, FloatField, IntField,
    ObjectIdField, ReferenceField, StringField,
)

from crm.models.custumer_model import Customer

LINES = ("Q30", "Q15", "Som", "Iluminação", "Vídeo", "Palco e praticáveis", "Acessórios")
BILLING_UNITS = ("metro", "unidade", "m²", "placa", "sistema", "par", "conjunto", "cachê")
RESERVATION_STATUSES = ("reservado", "retirado", "devolvido", "cancelado")
ACTIVE_RESERVATION_STATUSES = ("reservado", "retirado")
OBSERVATION_KINDS = ("nota", "ajuste")


class InventoryObservation(EmbeddedDocument):
    """Observação sobre o equipamento (estado, manutenção, onde está guardado) ou registro de
    ajuste de quantidade (entrada/baixa)."""

    id = ObjectIdField(default=ObjectId)
    kind = StringField(choices=OBSERVATION_KINDS, default='nota')
    text = StringField(required=True)
    author_id = StringField(null=True)
    author_name = StringField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {"id": str(self.id), "kind": self.kind, "text": self.text, "author_id": self.author_id,
                "author_name": self.author_name, "created_at": self.created_at.isoformat()}


class InventoryItem(Document):
    """Item de estoque. O preço de venda vem da tabela de preços (sales.catalog + LmSettings),
    pelo mesmo `code`; aqui ficam quantidade e dados físicos."""

    meta = {'collection': 'inventory_items', 'strict': False, 'indexes': ['code', 'line', 'active']}

    code = StringField(required=True, unique=True)
    line = StringField(choices=LINES, required=True)
    name = StringField(required=True)
    size = StringField(null=True)
    billing_unit = StringField(choices=BILLING_UNITS, default='unidade')
    qty_total = IntField(null=True)  # None = ainda não contado
    owned = BooleanField(default=True)  # False = terceirizado (LED, DJ): não bloqueia quantidade
    rentable = BooleanField(default=True)  # False = equipamento de apoio interno
    active = BooleanField(default=True)
    approximate_count = BooleanField(default=True)  # contagem de 22/01/2025, aproximada
    counted_at = DateTimeField(null=True)
    note = StringField(null=True)
    description = StringField(null=True)  # detalhes do equipamento (modelo, especificação, onde fica)
    observations = EmbeddedDocumentListField(InventoryObservation, default=list)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self, with_observations: bool = False) -> dict:
        data = {
            "id": str(self.id), "code": self.code, "line": self.line, "name": self.name, "size": self.size,
            "billing_unit": self.billing_unit, "qty_total": self.qty_total, "owned": self.owned,
            "rentable": self.rentable, "active": self.active, "approximate_count": self.approximate_count,
            "counted_at": self.counted_at.isoformat() if self.counted_at else None, "note": self.note,
            "description": self.description, "observations_count": len(self.observations or []),
        }
        if with_observations:
            data["observations"] = [o.to_dict() for o in sorted(self.observations or [], key=lambda o: o.created_at,
                                                                 reverse=True)]
        return data


class InventoryReservation(Document):
    meta = {'collection': 'inventory_reservations', 'strict': False,
            'indexes': ['item', 'proposal_id', 'status', ('item', 'status', 'start', 'end')]}

    item = ReferenceField(InventoryItem, required=True)
    proposal_id = StringField(null=True)  # None = reserva manual, feita na tela de estoque
    customer = ReferenceField(Customer, null=True, reverse_delete_rule=NULLIFY)
    client_name = StringField(null=True)  # reserva manual para quem ainda não é lead
    qty = FloatField(required=True)
    start = DateTimeField(required=True)
    end = DateTimeField(required=True)
    status = StringField(choices=RESERVATION_STATUSES, default='reservado')
    note = StringField(null=True)
    created_by = StringField(null=True)
    created_by_name = StringField(null=True)
    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id), "item_id": str(self.item.id), "item_code": self.item.code,
            "item_name": self.item.name, "proposal_id": self.proposal_id, "manual": self.proposal_id is None,
            "customer_id": str(self.customer.id) if self.customer else None,
            "customer_name": getattr(self.customer, 'name', None) or self.client_name, "qty": self.qty,
            "start": self.start.isoformat(), "end": self.end.isoformat(), "status": self.status,
            "note": self.note, "created_by": self.created_by, "created_by_name": self.created_by_name,
        }


class InventoryMovement(Document):
    meta = {'collection': 'inventory_movements', 'strict': False, 'indexes': ['item', 'customer', '-date']}

    item = ReferenceField(InventoryItem, required=True)
    customer = ReferenceField(Customer, null=True, reverse_delete_rule=NULLIFY)
    proposal_id = StringField(null=True)
    qty = FloatField(required=True)
    type = StringField(choices=('saida', 'retorno'), required=True)
    date = DateTimeField(default=datetime.utcnow)
    registered_by = StringField(null=True)
    note = StringField(null=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id), "item_code": self.item.code, "item_name": self.item.name,
            "customer_id": str(self.customer.id) if self.customer else None,
            "customer_name": getattr(self.customer, 'name', None), "proposal_id": self.proposal_id,
            "qty": self.qty, "type": self.type, "date": self.date.isoformat(),
            "registered_by": self.registered_by, "note": self.note,
        }
