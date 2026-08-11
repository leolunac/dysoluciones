from pathlib import Path
import os

# BASE DIRECTORY
BASE_DIR = Path(__file__).resolve().parent.parent


# ===============================
# SEGURIDAD
# ===============================

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "sigob-desarrollo-local-no-usar-en-produccion"
)

DEBUG = os.environ.get(
    "DJANGO_DEBUG",
    "True"
).lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost"
    ).split(",")
    if host.strip()
]


# ===============================
# APLICACIONES INSTALADAS
# ===============================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'portal_cliente',

    # App principal del sistema
    'operacion',
    'gestion_comercial',
]


# ===============================
# MIDDLEWARE
# ===============================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ===============================
# URLS PRINCIPAL
# ===============================

ROOT_URLCONF = 'sistema7x24.urls'


# ===============================
# TEMPLATES
# ===============================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Carpeta global de templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ===============================
# WSGI
# ===============================

WSGI_APPLICATION = 'sistema7x24.wsgi.application'


# ===============================
# BASE DE DATOS (POSTGRESQL)
# ===============================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",

        "NAME": os.environ.get(
            "POSTGRES_DB",
            "sistema7x24_db",
        ),

        "USER": os.environ.get(
            "POSTGRES_USER",
            "postgres",
        ),

        "PASSWORD": os.environ.get(
            "POSTGRES_PASSWORD",
            "",
        ),

        "HOST": os.environ.get(
            "POSTGRES_HOST",
            "localhost",
        ),

        "PORT": os.environ.get(
            "POSTGRES_PORT",
            "5432",
        ),
    }
}


# ===============================
# VALIDADORES DE PASSWORD
# ===============================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ===============================
# INTERNACIONALIZACIÓN
# ===============================

LANGUAGE_CODE = 'es-co'

TIME_ZONE = 'America/Bogota'

USE_I18N = True
USE_TZ = True


# ===============================
# ARCHIVOS ESTÁTICOS
# ===============================

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ===============================
# CONFIGURACIÓN LOGIN
# ===============================

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "/accounts/login/"



# ===============================
# DEFAULT PRIMARY KEY
# ===============================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'