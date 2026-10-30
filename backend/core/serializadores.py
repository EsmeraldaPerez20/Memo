from django.db.models.functions import Now
from rest_framework import serializers


def crear_serializador(modelo, nombre=None, fields="__all__", excluir=(), solo_lectura=(), extra=None):
    """ModelSerializer rapido. Los campos con fecha automatica de la base (db_default = now()) son de solo lectura."""
    automaticos = [f.name for f in modelo._meta.concrete_fields if isinstance(getattr(f, "db_default", None), Now)]
    meta = {"model": modelo, "read_only_fields": tuple(set(automaticos) | set(solo_lectura))}
    if excluir:
        meta["exclude"] = tuple(excluir)
    else:
        meta["fields"] = fields
    cuerpo = {"Meta": type("Meta", (), meta)}
    cuerpo.update(extra or {})
    return type(nombre or f"{modelo.__name__}Serializer", (serializers.ModelSerializer,), cuerpo)
