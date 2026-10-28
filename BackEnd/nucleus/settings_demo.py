"""Perfil de demonstração local, sem Docker: Mongo em memória, Redis falso e Celery eager.

Uso: python manage.py rundemo --settings=nucleus.settings_demo
Os dados somem ao parar o servidor. Nunca use em produção.
"""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "demo-only-secret-key")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("DB_USERNAME", "")
os.environ.setdefault("MONGO_PASSWORD", "")
os.environ.setdefault("MONGO_DB_NAME", "lm_test")
os.environ.setdefault("MONGO_HOST", "localhost")
os.environ.setdefault("MONGO_PORT", "27017")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
os.environ.setdefault("ZAPI_WEBHOOK_TOKEN", "demo-webhook-token")
os.environ.setdefault("OPENAI_API_KEY", "sk-demo-not-real")
os.environ.setdefault("ZAPI_BASE_URL", "http://zapi.invalid")

from .settings import *  # noqa: E402,F401,F403

import fakeredis  # noqa: E402
import mongomock  # noqa: E402
import mongomock.gridfs  # noqa: E402
import mongoengine  # noqa: E402
import redis  # noqa: E402

DEBUG = True

mongomock.gridfs.enable_gridfs_integration()  # arquivos da aba WhatsApp ficam no GridFS
mongoengine.disconnect_all()
mongoengine.connect(db="lm_demo", host="mongodb://localhost", mongo_client_class=mongomock.MongoClient)

_fake_redis_server = fakeredis.FakeServer()
redis.Redis.from_url = classmethod(lambda cls, *a, **kw: fakeredis.FakeRedis(server=_fake_redis_server))

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db_demo.sqlite3"}}  # noqa: F405

INSTALLED_APPS = [*INSTALLED_APPS, "devtools"]  # noqa: F405

CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
