from django.apps import apps
from django.contrib import admin

for modelo in apps.get_app_config("diagnostico").get_models():
    admin.site.register(modelo)
