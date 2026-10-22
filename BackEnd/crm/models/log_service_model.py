from mongoengine import Document, ReferenceField, StringField, DateTimeField, DictField
from datetime import datetime
from crm.models.custumer_model import Customer

class ServiceLog(Document):
    meta = {
        'collection': 'service_logs',
        'strict': False,
        'indexes': [
            'customer', 
            'operator_id',
            '-created_at'
        ]
    }

    customer = ReferenceField(Customer, reverse_delete_rule=2, required=True) 
    operator_id = StringField(null=True)
    opportunity_id = StringField(null=True)  # lead arquivado; vazio = lead atual
    
    ACTION_CHOICES = (
        ('LEAD_CREATED', 'Lead Novo Criado'),
        ('LEAD_UPDATED', 'Lead Atualizado'),
        ('LEAD_DELETED', 'Lead Excluído'),
        ('BUDGET_SENT', 'Orcamento Enviado'),
        ('NEGOTIATION_INTERACTION', 'Interacao em Negociacao'),
        ('STAGE_CHANGED', 'Mudanca de Etapa'),
        # Linha do tempo do card (processo com SDR)
        ('CALL_LOGGED', 'Ligação registrada'),
        ('NOTE_ADDED', 'Nota interna'),
        ('PROPOSAL_SENT', 'Proposta enviada'),
        ('MEETING_SCHEDULED', 'Agendamento'),
        ('APPROVAL_REQUESTED', 'Aprovação solicitada'),
        ('APPROVAL_DECIDED', 'Aprovação decidida'),
        ('LEAD_QUALIFIED', 'Lead qualificado'),
        ('FIELD_SAVED', 'Dado de qualificação salvo'),
        ('ATTACHMENT_ADDED', 'Anexo recebido'),
        ('HUMAN_OPERATOR', 'Encaminhado para operador humano'),
        ('FLAGS_CHANGED', 'Sinalizações alteradas'),
        ('NEXT_ACTION_SET', 'Próxima ação definida'),
        ('TASK_CREATED', 'Tarefa criada'),
        ('TASK_DONE', 'Tarefa concluída'),
        ('CONTACT_UPDATED', 'Contato atualizado'),
        ('NEW_LEAD_OPENED', 'Novo lead aberto'),
        ('FUNNEL_REMOVED', 'Card excluído do funil'),
        ('HANDOVER', 'Passagem entre IA e humano'),
        ('CONVERSATION_ASSIGNED', 'Conversa atribuída'),
    )
    action_type = StringField(choices=ACTION_CHOICES, required=True)
    description = StringField()
    metadata = DictField()  # detalhes estruturados (etapa de/para, resultado da ligação, ids)

    created_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "customer_id": str(self.customer.id) if self.customer else None,
            "operator_id": self.operator_id,
            "opportunity_id": self.opportunity_id,
            "action_type": self.action_type,
            "description": self.description,
            "metadata": dict(self.metadata or {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
