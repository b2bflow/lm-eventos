from mongoengine import Document, ReferenceField, StringField, DateTimeField
from datetime import datetime
from crm.models.custumer_model import Customer

class ServiceLog(Document):
    meta = {
        'collection': 'service_logs',
        'indexes': [
            'customer', 
            'operator_id',
            '-created_at'
        ]
    }

    customer = ReferenceField(Customer, reverse_delete_rule=2, required=True) 
    operator_id = StringField(null=True)
    
    ACTION_CHOICES = (
        ('LEAD_CREATED', 'Lead Novo Criado'),
        ('LEAD_UPDATED', 'Lead Atualizado'),
        ('LEAD_DELETED', 'Lead Excluído'),
        ('BUDGET_SENT', 'Orcamento Enviado'),
        ('NEGOTIATION_INTERACTION', 'Interacao em Negociacao'),
        ('STAGE_CHANGED', 'Mudanca de Etapa'),
    )
    action_type = StringField(choices=ACTION_CHOICES, required=True)
    description = StringField()

    created_at = DateTimeField(default=datetime.utcnow)
