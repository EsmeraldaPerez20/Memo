"""Configuracion de Django para el backend de Memo (FourMind).

Las 39 tablas las crea memo_schema.sql (Supabase); los modelos son managed = False.
Todo lo sensible se lee de variables de entorno (ver .env.example).
"""
import sys
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent
PRUEBAS = "test" in sys.argv

SECRET_KEY = config("SECRET_KEY", default="inseguro-solo-para-desarrollo")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "apps.usuarios",
    "apps.academico",
    "apps.documentos",
    "apps.tutor",
    "apps.evaluaciones",
    "apps.diagnostico",
    "apps.planificacion",
    "apps.administracion",
]

AUTH_USER_MODEL = "usuarios.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# ---------------------------------------------------------------- base de datos (Supabase / PostgreSQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="postgres"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        "OPTIONS": {"sslmode": config("DB_SSLMODE", default="require")},
    }
}
# Para las pruebas: base local con el esquema ya cargado (memo_schema.sql) que se usa como plantilla.
if config("TEST_DB_TEMPLATE", default=""):
    DATABASES["default"]["TEST"] = {"TEMPLATE": config("TEST_DB_TEMPLATE")}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}


# ---------------------------------------------------------------- API REST
def _tasa(normal, pruebas="100000/min"):
    return pruebas if PRUEBAS else normal


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.paginacion.PaginacionEstandar",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"user": _tasa("1000/min"), "auth": _tasa("20/min"), "ia": _tasa("30/min")},
    "EXCEPTION_HANDLER": "core.errores.manejador",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MIN", default=30, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DIAS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.usuarios.serializers.LoginSerializer",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Memo (FourMind) API",
    "DESCRIPTION": "Backend del tutor virtual academico con IA. Autenticacion: Authorization: Bearer <access>.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173,http://localhost:3000", cast=Csv())

# ---------------------------------------------------------------- correo (recuperacion de contrasena, notificaciones)
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Memo <no-reply@memo.local>")
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")

# ---------------------------------------------------------------- inteligencia artificial
# "simulado" permite desarrollar y probar sin gastar creditos ni tener claves.
IA_PROVEEDOR = config("IA_PROVEEDOR", default="simulado")            # simulado | anthropic | openai
IA_MODELO = config("IA_MODELO", default="")                          # vacio = modelo economico por defecto
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
EMBEDDINGS_PROVEEDOR = config("EMBEDDINGS_PROVEEDOR", default="simulado")   # simulado | openai
EMBEDDING_MODELO = config("EMBEDDING_MODELO", default="text-embedding-3-small")
EMBEDDING_DIM = 1536            # debe coincidir con fragmentos.embedding vector(1536)
IA_PRECIO_ENTRADA_USD_POR_M = config("IA_PRECIO_ENTRADA_USD_POR_M", default=0.0, cast=float)
IA_PRECIO_SALIDA_USD_POR_M = config("IA_PRECIO_SALIDA_USD_POR_M", default=0.0, cast=float)
RAG_TOP_K = config("RAG_TOP_K", default=4, cast=int)
RAG_DISTANCIA_MAXIMA = config("RAG_DISTANCIA_MAXIMA", default=0.75, cast=float)

# ---------------------------------------------------------------- almacenamiento privado de archivos
SUPABASE_URL = config("SUPABASE_URL", default="")                     # https://xxxx.supabase.co
SUPABASE_SERVICE_KEY = config("SUPABASE_SERVICE_KEY", default="")     # solo en el servidor, nunca en el frontend
SUPABASE_BUCKET = config("SUPABASE_BUCKET", default="documentos")     # bucket PRIVADO
ALMACENAMIENTO_LOCAL = Path(config("ALMACENAMIENTO_LOCAL", default=str(BASE_DIR / "almacenamiento_local")))

GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")

# ---------------------------------------------------------------- seguridad en produccion (Render)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if config("FORZAR_HTTPS", default=False, cast=bool):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
