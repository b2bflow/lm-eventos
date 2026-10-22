from datetime import datetime

from mongoengine import DateTimeField, DictField, Document, ReferenceField, StringField

from crm.models.custumer_model import Customer

TASK_TYPES = {
    'ligar_15min': 'Ligar para o lead qualificado',
    'follow_up_d1': 'Follow-up D+1 (ligação)',
    'follow_up_d3': 'Follow-up D+3 (WhatsApp)',
    'follow_up_d5': 'Follow-up D+5 (ligação)',
    'proposta_vencendo': 'Proposta vence amanhã',
    'reuniao_amanha': 'Reunião amanhã',
    'retomar_lead_parado': 'Retomar lead parado',
    'reativar_lead': 'Reativar lead perdido sem resposta',
    # Atividades criadas à mão na página do lead (título livre em metadata.title)
    'atividade_ligacao': 'Ligação',
    'atividade_whatsapp': 'WhatsApp',
    'atividade_reuniao': 'Reunião',
    'atividade_email': 'E-mail',
    'atividade_tarefa': 'Tarefa',
}

MANUAL_TASK_TYPES = tuple(t for t in TASK_TYPES if t.startswith('atividade_'))

# Tarefas da cadência de uma proposta enviada: canceladas quando o lead sai de PROPOSAL_SENT
# ou quando uma nova versão é enviada (novo ciclo).
CADENCE_TASKS = ('follow_up_d1', 'follow_up_d3', 'follow_up_d5', 'proposta_vencendo')

TASK_STATUSES = ('pending', 'done', 'canceled')


class SdrTask(Document):
    """Tarefa da fila da SDR (gerada pela plataforma; contatos de operador humano nunca entram)."""

    meta = {
        'collection': 'sdr_tasks',
        'strict': False,
        'indexes': ['customer', 'status', 'due_at', ('status', 'due_at'), 'type'],
    }

    customer = ReferenceField(Customer, required=True, reverse_delete_rule=2)
    type = StringField(choices=tuple(TASK_TYPES), required=True)
    due_at = DateTimeField(required=True)
    assignee = StringField(default='sdr')
    status = StringField(choices=TASK_STATUSES, default='pending')
    done_at = DateTimeField(null=True)
    done_by = StringField(null=True)
    metadata = DictField()
    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        customer = self.customer
        label = TASK_TYPES.get(self.type, self.type)
        title = (self.metadata or {}).get('title')
        return {
            "id": str(self.id),
            "customer_id": str(customer.id) if customer else None,
            "customer_name": getattr(customer, 'name', None),
            "customer_phone": getattr(customer, 'phone', None),
            "type": self.type,
            "label": f"{label}: {title}" if title else label,
            "title": title,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "assignee": self.assignee,
            "status": self.status,
            "done_at": self.done_at.isoformat() if self.done_at else None,
            "metadata": dict(self.metadata or {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
