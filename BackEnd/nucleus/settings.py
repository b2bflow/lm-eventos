from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv
import mongoengine
import os


BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS','').split(',')
ROOT_URLCONF = 'nucleus.urls'
WSGI_APPLICATION = 'nucleus.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    # Refresh token revogável: logout e rotação põem o token antigo na lista negra.
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',

    'core',
    'crm',
    'chat',
    'analytics',
    'users',
    'events',
    'gateway',
    'ai_agents',
    # Processo comercial com SDR
    'sales',
    'inventory',
    'agenda',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'users.middleware.UpdateLastLoginMiddleware',
]


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        # Em produção aponte SQLITE_PATH para um volume (ex.: /data/db.sqlite3): sem isso os
        # usuários do painel somem a cada deploy.
        'NAME': os.getenv('SQLITE_PATH') or BASE_DIR / 'db.sqlite3',
    }
}

mongo_user = os.getenv('DB_USERNAME').strip()
mongo_pass = os.getenv('MONGO_PASSWORD').strip()
mongo_db = os.getenv('MONGO_DB_NAME').strip()
mongo_host = os.getenv('MONGO_HOST').strip()
mongo_port = int(os.getenv('MONGO_PORT'))


if mongo_user and mongo_pass:
    mongoengine.connect(
        db=mongo_db,
        host=mongo_host,
        port=mongo_port,
        username=mongo_user,
        password=mongo_pass,
        authentication_source='admin'
    )
else:
    mongoengine.connect(db=mongo_db, host=mongo_host, port=mongo_port)


AUTH_USER_MODEL = 'users.User'
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle"
    ],
    # Por minuto, não por dia: o painel faz polling (barra lateral a cada 30 s, leads a cada 4 s) e
    # "1000/day" bloqueava a SDR com 429 no meio do expediente.
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("API_ANON_THROTTLE", "10/minute"),
        "user": os.getenv("API_USER_THROTTLE", "300/minute"),
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}

SIMPLE_JWT = {
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY', SECRET_KEY),
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    # Cada /token/refresh/ devolve um refresh novo e invalida o anterior: um refresh vazado
    # deixa de valer assim que o painel renova a sessão.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}


CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')

# --- Produção (DEBUG=False) ---------------------------------------------------------------
# Atrás de proxy com HTTPS (nginx, Traefik): SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO.
if os.getenv('SECURE_PROXY_SSL_HEADER'):
    SECURE_PROXY_SSL_HEADER = (os.getenv('SECURE_PROXY_SSL_HEADER'), 'https')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '0'))  # ex.: 31536000 depois de confirmar o HTTPS
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT') == 'True'
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # webhook e formulários; importação de CSV tem limite próprio (2 MB)

# Admin do Django desligado por padrão: o login dele não tem limite de tentativas e serviria para
# testar senhas da equipe. Ligar só quando precisar (DJANGO_ADMIN_ENABLED=True).
DJANGO_ADMIN_ENABLED = os.getenv('DJANGO_ADMIN_ENABLED') == 'True'

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]



CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
# Horários do beat (crontab) em horário de Brasília; datas no banco seguem em UTC.
CELERY_TIMEZONE = 'America/Sao_Paulo'
CELERY_ENABLE_UTC = True

# Tarefas periódicas (rodar `celery -A nucleus beat`). Ver BackEnd/README.md.
from nucleus.beat_schedule import CELERY_BEAT_SCHEDULE  # noqa: E402,F401

# Fuso usado nas regras de negócio (horário comercial, prazos da SDR, agenda).
LM_TIMEZONE = os.getenv('LM_TIMEZONE', 'America/Sao_Paulo')

ZAPI_SECURITY_TOKEN = os.getenv('ZAPI_SECURITY_TOKEN')
ZAPI_INSTANCE_ID = os.getenv('ZAPI_INSTANCE_ID')
ZAPI_TOKEN = os.getenv('ZAPI_TOKEN')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')