from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.auditoria import registrar
from core.permisos import EsPersonalAcademico, tiene_permiso
from core.viewsets import DuenioMixin
from servicios import tutor as servicio_tutor

from .models import Conversacion, Mensaje, ReporteIA
from .serializers import (ConversacionSerializer, MensajeSerializer, PreguntarSerializer, ReportarSerializer, ReporteIASerializer)


class ConversacionViewSet(DuenioMixin, viewsets.ModelViewSet):
    """Conversaciones con el tutor (RF-06 a RF-12). 'guardada' es el consentimiento para conservar el historial (RF-10, RF-11)."""
    queryset = Conversacion.objects.select_related("materia", "documento").order_by("-fecha_ultima_actividad")
    serializer_class = ConversacionSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("tutor.usar")]
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ["materia", "documento", "guardada"]
    search_fields = ["titulo"]

    def destroy(self, request, *args, **kwargs):
        """RF-11: borra la conversacion; la base elimina sus mensajes y fuentes (los reportes conservan una copia)."""
        c = self.get_object()
        c.delete()
        registrar(request, "eliminar_conversacion", entidad="conversaciones", entidad_id=kwargs.get("pk"))
        return Response(status=204)

    @extend_schema(responses=MensajeSerializer(many=True))
    @action(detail=True, methods=["get"])
    def mensajes(self, request, pk=None):
        qs = Mensaje.objects.filter(conversacion=self.get_object()).order_by("id")
        return Response(MensajeSerializer(qs, many=True).data)

    @extend_schema(request=PreguntarSerializer, responses={201: MensajeSerializer})
    @action(detail=True, methods=["post"], throttle_scope="ia")
    def preguntar(self, request, pk=None):
        """Envia una pregunta al tutor y devuelve su respuesta con las fuentes que la respaldan (RF-53)."""
        s = PreguntarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        respuesta = servicio_tutor.responder(self.get_object(), request.user, s.validated_data["contenido"], s.validated_data["modo_explicacion"])
        return Response(MensajeSerializer(respuesta).data, status=201)


class ReportarMensajeView(APIView):
    """RF-52: el estudiante reporta una respuesta incorrecta de la IA. Se guarda una copia del texto reportado."""
    permission_classes = [IsAuthenticated, tiene_permiso("ia.reportar_respuesta")]

    @extend_schema(request=ReportarSerializer, responses={201: ReporteIASerializer})
    def post(self, request, pk):
        mensaje = get_object_or_404(Mensaje.objects.select_related("conversacion"), pk=pk, emisor="ia", conversacion__usuario=request.user)
        s = ReportarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        r = ReporteIA.objects.create(mensaje=mensaje, usuario=request.user, contenido_reportado=mensaje.contenido,
                                     motivo=s.validated_data["motivo"], comentario=s.validated_data.get("comentario") or None)
        registrar(request, "reportar_respuesta_ia", entidad="mensajes", entidad_id=mensaje.id)
        return Response(ReporteIASerializer(r).data, status=201)


class ReporteIAViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Revision de respuestas reportadas (docentes y administradores)."""
    queryset = ReporteIA.objects.order_by("-fecha_reporte")
    serializer_class = ReporteIASerializer
    permission_classes = [IsAuthenticated, EsPersonalAcademico]
    http_method_names = ["get", "patch"]
    filterset_fields = ["estado", "motivo"]

    def perform_update(self, serializer):
        serializer.save(revisado_por=self.request.user, fecha_revision=timezone.now())
