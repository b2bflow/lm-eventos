"""Settings para a suíte de testes: Mongo em memória (mongomock), Celery eager e sem Redis real."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("ALLOWED_HOSTS", "testserver,localhost")
os.environ.setdefault("ZAPI_WEBHOOK_TOKEN", "test-webhook-token")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ZAPI_BASE_URL", "http://zapi.invalid")
os.environ.setdefault("DB_USERNAME", "")
os.environ.setdefault("MONGO_PASSWORD", "")
os.environ.setdefault("MONGO_DB_NAME", "lm_test")
os.environ.setdefault("MONGO_HOST", "localhost")
os.environ.setdefault("MONGO_PORT", "27017")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

from .settings import *  # noqa: E402,F401,F403

import mongomock  # noqa: E402
import mongomock.gridfs  # noqa: E402
import mongoengine  # noqa: E402

mongomock.gridfs.enable_gridfs_integration()  # arquivos da aba WhatsApp ficam no GridFS
mongoengine.disconnect_all()
mongoengine.connect(
    db="lm_test",
    host="mongodb://localhost",
    mongo_client_class=mongomock.MongoClient,
    uuidRepresentation="standard",
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
}
