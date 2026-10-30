from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permisos import EsPersonalAcademico, PermisosPorAccion, tiene_permiso
from core.viewsets import DuenioMixin
from servicios import evaluacion as ev

from .models import Actividad, BancoPregunta, Intento, Respuesta
from .serializers import (ActividadDetalleSerializer, ActividadSerializer, BancoPreguntaSerializer, GenerarActividadSerializer,
                          IntentoSerializer, ResponderSerializer)


class BancoPreguntaViewSet(viewsets.ModelViewSet):
    """Banco de preguntas (docentes y administradores). Los estudiantes nunca ven las respuestas por aqui (RF-35)."""
    queryset = BancoPregunta.objects.select_related("tema").order_by("-id")
    serializer_class = BancoPreguntaSerializer
    permission_classes = [IsAuthenticated, EsPersonalAcademico]
    filterset_fields = ["tema", "tipo", "dificultad", "validada", "origen"]
    search_fields = ["enunciado"]

    def perform_create(self, serializer):
        serializer.save(origen="docente")


class ActividadViewSet(PermisosPorAccion, DuenioMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin,
                       viewsets.GenericViewSet):
    """Ejercicios, quizzes, simulacros y examenes del estudiante (RF-26 a RF-36)."""
    queryset = Actividad.objects.select_related("materia").order_by("-fecha_creacion")
    permisos_por_accion = {"generar": [IsAuthenticated, tiene_permiso("actividades.generar")], "*": [IsAuthenticated]}
    filterset_fields = ["materia", "tipo", "dificultad"]

    def get_serializer_class(self):
        return ActividadDetalleSerializer if self.action == "retrieve" else ActividadSerializer

    @extend_schema(request=GenerarActividadSerializer, responses={201: ActividadDetalleSerializer})
    @action(detail=False, methods=["post"], throttle_scope="ia")
    def generar(self, request):
        """Arma una actividad con preguntas del banco y, si faltan, las genera con IA. 'adaptativa' ajusta la dificultad por tema."""
        s = GenerarActividadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            act = ev.generar_actividad(request.user, d["materia"], d["temas"], d["tipo"], d["dificultad"], d["num_preguntas"],
                                       d.get("limite_tiempo_min"), d["adaptativa"], d.get("tipos_pregunta"), d.get("titulo"))
        except ev.ErrorEvaluacion as e:
            raise serializers.ValidationError({"detail": str(e)})
        return Response(ActividadDetalleSerializer(act, context=self.get_serializer_context()).data, status=201)

    @extend_schema(request=None, responses={201: IntentoSerializer})
    @action(detail=True, methods=["post"])
    def iniciar(self, request, pk=None):
        """Empieza (o retoma) un intento. Devuelve las preguntas sin respuestas y el limite de tiempo."""
        actividad = self.get_object()
        intento = ev.iniciar_intento(actividad, request.user)
        datos = IntentoSerializer(intento).data
        datos["limite_tiempo_min"] = actividad.limite_tiempo_min
        datos["preguntas"] = ev.preguntas_de(actividad)
        return Response(datos, status=201)


class IntentoViewSet(DuenioMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Historial de intentos y resultados (RF-31, RF-36)."""
    queryset = Intento.objects.select_related("actividad").order_by("-id")
    serializer_class = IntentoSerializer
    filterset_fields = ["actividad", "estado", "actividad__materia"]
    ordering_fields = ["id", "fecha_inicio", "calificacion"]

    @extend_schema(request=ResponderSerializer, responses={200: {"type": "object"}})
    @action(detail=True, methods=["post"])
    def responder(self, request, pk=None):
        """Guarda la respuesta a una pregunta. En 'ejercicio' devuelve la retroalimentacion al instante; en quiz/examen, al finalizar."""
        intento = self.get_object()
        s = ResponderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            r = ev.responder(intento, s.validated_data["pregunta"], s.validated_data["respuesta"], s.validated_data.get("tiempo_segundos"))
        except ev.ErrorEvaluacion as e:
            raise serializers.ValidationError({"detail": str(e)})
        if intento.actividad.tipo == "ejercicio":
            return Response({"es_correcta": r.es_correcta, "puntaje": float(r.puntaje), "retroalimentacion": r.retroalimentacion})
        return Response({"guardada": True})

    @extend_schema(request=None, responses=IntentoSerializer)
    @action(detail=True, methods=["post"])
    def finalizar(self, request, pk=None):
        """Califica el intento, valida el tiempo en el servidor y actualiza el progreso y las dificultades del estudiante."""
        intento = ev.finalizar(self.get_object())
        return Response(IntentoSerializer(intento).data)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"])
    def resultado(self, request, pk=None):
        """Detalle con respuestas correctas y explicaciones (solo cuando el intento ya termino, RF-33)."""
        intento = self.get_object()
        if intento.estado == "en_curso":
            raise serializers.ValidationError({"detail": "Finaliza el intento para ver el resultado."})
        respuestas = {r.pregunta_id: r for r in Respuesta.objects.filter(intento=intento)}
        detalle = []
        for p in ev.preguntas_de(intento.actividad, con_respuestas=True):
            r = respuestas.get(p["id"])
            p.update(respuesta_usuario=r.respuesta_usuario if r else None, es_correcta=r.es_correcta if r else False,
                     puntaje=float(r.puntaje) if r and r.puntaje is not None else 0.0, retroalimentacion=r.retroalimentacion if r else "Sin respuesta")
            detalle.append(p)
        return Response({"intento": IntentoSerializer(intento).data, "preguntas": detalle})
