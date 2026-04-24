from mongoengine import Document, StringField, BooleanField

class SystemConfig(Document):
    meta = {
        'collection': 'system_configs',
        'strict': False
    }
    
    webhook_token = StringField(default="")
    zapi_instance_id = StringField(default="")
    zapi_token = StringField(default="")

    openai_api_key = StringField(default="")
    ai_active = BooleanField(default=True)