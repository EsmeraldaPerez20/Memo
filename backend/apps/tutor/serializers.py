from rest_framework import serializers

from core.serializadores import crear_serializador
from servicios import tutor as servicio_tutor

from .models import Conversacion, Mensaje, ReporteIA

_Base = crear_serializador(Conversacion, "ConversacionBase", solo_lectura=("usuario",))


class ConversacionSerializer(_Base):
    def validate_documento(self, d):
        if d is not None and (d.usuario_id != self.context["request"].user.id or d.fecha_eliminacion is not None):
            raise serializers.ValidationError("Ese documento no esta disponible.")
        return d


class MensajeSerializer(serializers.ModelSerializer):
    fuentes = serializers.SerializerMethodField()

    class Meta:
        model = Mensaje
        fields = ["id", "emisor", "contenido", "modo_explicacion", "advertencia_ia", "fecha_envio", "fuentes"]

    def get_fuentes(self, m):
        return servicio_tutor.fuentes_de(m) if m.emisor == "ia" else []


class PreguntarSerializer(serializers.Serializer):
    contenido = serializers.CharField(max_length=4000)
    modo_explicacion = serializers.ChoiceField(choices=list(servicio_tutor.INSTRUCCION_MODO), default="normal")


class ReportarSerializer(serializers.Serializer):
    motivo = serializers.ChoiceField(choices=["incorrecta", "incompleta", "inapropiada", "otro"])
    comentario = serializers.CharField(required=False, allow_blank=True)


ReporteIASerializer = crear_serializador(
    ReporteIA, solo_lectura=("mensaje", "contenido_reportado", "usuario", "motivo", "comentario", "fecha_reporte", "fecha_revision", "revisado_por"))
