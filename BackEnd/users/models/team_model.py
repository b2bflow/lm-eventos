from mongoengine import Document, StringField, ListField, DateTimeField
from datetime import datetime

class Team(Document):
    meta = {'collection': 'teams'}
    
    name = StringField(required=True, unique=True)
    description = StringField(default="")
    members = ListField(StringField(), default=list) 
    created_at = DateTimeField(default=datetime.utcnow)