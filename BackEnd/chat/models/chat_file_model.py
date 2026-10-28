from datetime import datetime

from mongoengine import CASCADE, DateTimeField, Document, FileField, IntField, ReferenceField, StringField

from .conversation_model import ConversationModel


class ChatFile(Document):
    """Arquivo que o operador mandou pela aba WhatsApp (GridFS: aceita arquivos acima de 16 MB).

    Fica guardado para a conversa mostrar o arquivo e para a Z-API baixar os grandes por link.
    """
    meta = {"collection": "chat_files", "indexes": ["conversation"]}

    conversation = ReferenceField(ConversationModel, reverse_delete_rule=CASCADE)
    data = FileField(collection_name="chat_files_fs")
    file_name = StringField(required=True)
    content_type = StringField()
    size = IntField()
    created_at = DateTimeField(default=datetime.utcnow)
