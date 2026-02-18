import json
from mongoengine import Document, StringField, ReferenceField, DateTimeField
from datetime import datetime
from .customer_model import Customer


class Message(Document):
    meta = {"collection": "messages"}

    customer_id = ReferenceField(
        Customer, required=True, reverse_delete_rule=2
    )  # CASCADE
    role = StringField(required=True)
    content = StringField(required=True)
    created_at = DateTimeField(default=datetime.now())

    def to_dict(self) -> dict:
        data = {
            "id": str(self.id),
            "customer_id": str(self.customer_id.id) if self.customer_id else None,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }

        try:
            content = json.loads(self.content)

            data["content"] = (
                content if isinstance(content, (dict, list)) else str(self.content)
            )
        except (json.JSONDecodeError, TypeError):
            data["content"] = str(self.content)

        return data
