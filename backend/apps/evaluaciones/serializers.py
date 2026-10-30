from rest_framework import serializers

from apps.academico.models import Materia, Tema
from core.serializadores import crear_serializador
from servicios import evaluacion as ev

from .models import Actividad, BancoPregunta, Intento

_BancoBase = crear_serializador(BancoPregunta, "BancoBase", solo_lectura=("origen",))


class BancoPreguntaSerializer(_BancoBase):
    """Pregunta del banco. Valida que 'opciones' y 'respuesta_correcta' tengan el formato de su tipo."""
    respuesta_correcta = serializers.JSONField(help_text="Texto, o lista/objeto JSON para completar espacios y relacionar columnas")

    def validate(self, attrs):
        base = {f: attrs.get(f, getattr(self.instance, f, None)) for f in ("tipo", "enunciado", "opciones", "respuesta_correcta", "explicacion")}
        limpia = ev._limpiar(base, ev.TIPOS_PREGUNTA)
        if limpia is None:
            raise serializers.ValidationError("Formato invalido: revisa 'opciones' y 'respuesta_correcta' segun el tipo de pregunta.")
        attrs["respuesta_correcta"], attrs["opciones"] = limpia["respuesta_correcta"], limpia["opciones"]
        return attrs


ActividadSerializer = crear_serializador(Actividad, "ActividadSerializer", solo_lectura=("usuario", "num_preguntas", "generada_por"))


class ActividadDetalleSerializer(ActividadSerializer):
    preguntas = serializers.SerializerMethodField()

    def get_preguntas(self, a):
        return ev.preguntas_de(a)


class GenerarActividadSerializer(serializers.Serializer):
    materia = serializers.PrimaryKeyRelatedField(queryset=Materia.objects.filter(activa=True))
    temas = serializers.PrimaryKeyRelatedField(queryset=Tema.objects.all(), many=True, allow_empty=False)
    tipo = serializers.ChoiceField(choices=["ejercicio", "quiz", "simulacro", "examen"], default="quiz")
    dificultad = serializers.ChoiceField(choices=["baja", "media", "alta"], default="media")
    num_preguntas = serializers.IntegerField(min_value=1, max_value=50, default=5)
    limite_tiempo_min = serializers.IntegerField(min_value=1, max_value=480, required=False, allow_null=True)
    adaptativa = serializers.BooleanField(default=False, help_text="Ajusta la dificultad de cada tema al dominio del estudiante")
    tipos_pregunta = serializers.ListField(child=serializers.ChoiceField(choices=list(ev.TIPOS_PREGUNTA)), required=False)
    titulo = serializers.CharField(max_length=200, required=False)

    def validate(self, d):
        ajenos = [t.id for t in d["temas"] if t.unidad.materia_id != d["materia"].id]
        if ajenos:
            raise serializers.ValidationError({"temas": f"Los temas {ajenos} no pertenecen a la materia elegida."})
        return d


IntentoSerializer = crear_serializador(
    Intento, "IntentoSerializer", solo_lectura=("actividad", "usuario", "numero_intento", "estado", "calificacion", "tiempo_segundos", "retroalimentacion", "fecha_fin"),
    extra={"actividad_titulo": serializers.CharField(source="actividad.titulo", read_only=True)})


class ResponderSerializer(serializers.Serializer):
    pregunta = serializers.IntegerField()
    respuesta = serializers.JSONField(help_text='Texto, "verdadero"/"falso", {"1":"b"} para relacionar o ["a","b"] para completar')
    tiempo_segundos = serializers.IntegerField(min_value=0, required=False, allow_null=True)
