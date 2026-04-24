from rest_framework import serializers
from rest_framework_mongoengine.serializers import DocumentSerializer
from chat.models.conversation_model import ConversationModel
from chat.models.message_model import MessageModel

class ConversationSerializer(DocumentSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default="Desconhecido")
    customer_phone = serializers.CharField(source='customer.phone', read_only=True, default="Sem Número")
    customer_status = serializers.CharField(source='customer.customer_state_now', read_only=True, default="ANALYSIS")
    
    last_interaction_at = serializers.DateTimeField(source='updated_at', read_only=True)
    past_conversations = serializers.SerializerMethodField()
    final_customer_status = serializers.CharField(read_only=True)
    needs_attention = serializers.BooleanField(read_only=True) 
    

    class Meta:
        model = ConversationModel
        fields = [
            'id', 'customer', 'customer_name', 'customer_phone', 'customer_status', 
            'status', 'tag', 'ai_active', 'last_message_content', 
            'last_interaction_at', 'unread_count', 'created_at',
            'final_customer_status', 'past_conversations', 
            'needs_attention' 
        ]

    def get_past_conversations(self, obj):
        try:
            past = ConversationModel.objects(customer=obj.customer, id__ne=obj.id).only('id', 'created_at', 'status', 'final_customer_status', 'customer').order_by('-created_at')
            return [
                {
                    "id": str(c.id),
                    "created_at": c.created_at.isoformat(),
                    "status": c.status,
                    "final_customer_status": getattr(c, 'final_customer_status', getattr(c.customer, 'customer_state_now', 'ANALYSIS'))
                } for c in past
            ]
        except Exception:
            return []

class MessageSerializer(DocumentSerializer):
    conversation_id = serializers.CharField(source='conversation.id', read_only=True)
    class Meta:
        model = MessageModel
        fields = [
            'id', 'conversation_id', 'role', 'direction', 
            'status', 'message_type', 'content', 'media_url', 'created_at'
        ]
