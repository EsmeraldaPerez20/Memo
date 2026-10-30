from rest_framework import serializers

from apps.academico.models import Materia, Tema
from core.serializadores import crear_serializador
from servicios import configuracion

from .models import Documento, ElementoDocumento, Material

EXTENSIONES = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt", "png": "png", "jpg": "jpg", "jpeg": "jpg"}
LIMITE_DURO_MB = 20        # el schema tambien lo exige con un CHECK (RF-14)


def validar_archivo(f):
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in EXTENSIONES:
        raise serializers.ValidationError("Formato no permitido. Usa PDF, Word, PowerPoint, TXT, PNG o JPG.")
    limite = min(int(configuracion.obtener("max_archivo_mb", 20)), LIMITE_DURO_MB)
    if f.size > limite * 1024 * 1024:
        raise serializers.ValidationError(f"El archivo supera el limite de {limite} MB.")
    if f.size == 0:
        raise serializers.ValidationError("El archivo esta vacio.")
    return f


class SubirDocumentoSerializer(serializers.Serializer):
    archivo = serializers.FileField(validators=[validar_archivo])
    materia = serializers.PrimaryKeyRelatedField(queryset=Materia.objects.filter(activa=True), required=False, allow_null=True)
    analizar = serializers.BooleanField(default=False, help_text="Analizar el documento inmediatamente despues de subirlo")


class SubirMaterialSerializer(serializers.Serializer):
    archivo = serializers.FileField(validators=[validar_archivo])
    materia = serializers.PrimaryKeyRelatedField(queryset=Materia.objects.filter(activa=True))
    tema = serializers.PrimaryKeyRelatedField(queryset=Tema.objects.all(), required=False, allow_null=True)
    titulo = serializers.CharField(max_length=200)
    descripcion = serializers.CharField(required=False, allow_blank=True)


DocumentoSerializer = crear_serializador(
    Documento, excluir=("archivo_url", "usuario"),
    solo_lectura=("tipo_archivo", "tamano_bytes", "estado_analisis", "fecha_analisis", "fecha_eliminacion"))
ElementoSerializer = crear_serializador(ElementoDocumento, excluir=("documento",))
MaterialSerializer = crear_serializador(
    Material, excluir=("archivo_url",),
    solo_lectura=("tipo_archivo", "tamano_bytes", "subido_por", "estado", "revisado_por", "comentarios_revision",
                  "fecha_revision", "fecha_publicacion", "fecha_subida", "materia"))
