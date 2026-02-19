from mongoengine import Document, StringField, DateTimeField, DictField, BooleanField
from datetime import datetime


class Manager(Document):
    meta = {"collection": "managers"}

    name = StringField(required=True)
    email = StringField(required=True, unique=True)
    password_hash = StringField(required=True)
    session_token = StringField()
    created_at = DateTimeField(default=datetime.now())
    updated_at = DateTimeField(default=datetime.now())

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    def to_dict(self) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "password_hash": self.password_hash,
            "session_token": self.session_token,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        return data