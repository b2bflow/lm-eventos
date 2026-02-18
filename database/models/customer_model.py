from mongoengine import Document, StringField, DateTimeField
from datetime import datetime


class Customer(Document):
    meta = {"collection": "customers"}

    name = StringField(required=True)
    phone = StringField(required=True, unique=True)
    agent = StringField()
    address = StringField()
    created_at = DateTimeField(default=datetime.now())
    updated_at = DateTimeField(default=datetime.now())

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    def to_dict(self) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "phone": self.phone,
            "agent": self.agent,
            "address": self.address,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        return data
