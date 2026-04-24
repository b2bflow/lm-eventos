import json
from mongoengine import Document, ReferenceField, StringField, DateTimeField, DictField
from datetime import datetime
from .conversation_model import ConversationModel
from crm.models.custumer_model import Customer

class MessageModel(Document):
    meta = {
        'collection': 'messages',
        'strict': False,
        'indexes': [
            'conversation',
            'customer',
            'status',            
            'external_id',       
            '-created_at'        
        ]
    }

    conversation = ReferenceField(ConversationModel, required=True, reverse_delete_rule=2)
    
    customer = ReferenceField(Customer, required=True, reverse_delete_rule=2)

    external_id = StringField(unique=True, sparse=True)

    role = StringField(required=True)

    DIRECTION_CHOICES = (
        ('INCOMING', 'Entrada (Paciente)'), 
        ('OUTGOING', 'Saída (Operador/IA)')
    )
    direction = StringField(choices=DIRECTION_CHOICES, required=True)

    STATUS_CHOICES = (
        ('QUEUED', 'Na Fila de Envio'),           
        ('SENT_TO_GATEWAY', 'Enviada para API'),  
        ('DELIVERED', 'Entregue no Celular'),     
        ('READ', 'Lida pelo Paciente'),               
        ('FAILED', 'Falha no Envio'),             
        ('RECEIVED', 'Recebida do Paciente')          
    )
    status = StringField(choices=STATUS_CHOICES, default='QUEUED')
    
    error_message = StringField()

    CONTENT_TYPE_CHOICES = (('text', 'Texto'), ('image', 'Imagem'), ('audio', 'Áudio'), ('file', 'Arquivo'))
    message_type = StringField(choices=CONTENT_TYPE_CHOICES, default='text')
    
    content = StringField(required=True)  
    media_url = StringField() 

    raw_metadata = DictField()

    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def to_dict(self) -> dict:
        data = {
            "id": str(self.id),
            "conversation_id": str(self.conversation.id) if self.conversation else None,
            "customer_id": str(self.customer.id) if self.customer else None,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

        try:
            data["content"] = json.loads(self.content)
        except (json.JSONDecodeError, TypeError, ValueError):
            data["content"] = str(self.content)

        return data