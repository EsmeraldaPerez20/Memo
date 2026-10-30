from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permisos import PermisosPorAccion, tiene_permiso
from core.serializadores import crear_serializador
from core.viewsets import DuenioMixin

from .models import BitacoraAuditoria, ConfiguracionSistema, ConsumoIA, Incidencia, Notificacion

NotificacionSerializer = crear_serializador(
    Notificacion, "NotificacionSerializer", solo_lectura=("usuario", "tipo", "titulo", "mensaje", "canal", "fecha_programada", "fecha_envio"))
BitacoraSerializer = crear_serializador(BitacoraAuditoria, "BitacoraSerializer")
IncidenciaSerializer = crear_serializador(Incidencia, "IncidenciaSerializer", solo_lectura=("reportada_por", "fecha_resolucion"))
ConsumoSerializer = crear_serializador(ConsumoIA, "ConsumoSerializer")
ConfiguracionSerializer = crear_serializador(ConfiguracionSistema, "ConfiguracionSerializer", solo_lectura=("actualizado_por",))


class NotificacionViewSet(DuenioMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Notificaciones del usuario (RF-54). Solo se puede marcar 'leida'."""
    queryset = Notificacion.objects.order_by("-fecha_creacion")
    serializer_class = NotificacionSerializer
    http_method_names = ["get", "post", "patch"]
    filterset_fields = ["leida", "tipo", "canal"]

    @extend_schema(request=None, responses={200: {"type": "object"}})
    @action(detail=False, methods=["post"], url_path="marcar-todas")
    def marcar_todas(self, request):
        n = Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
        return Response({"marcadas": n})

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=False, methods=["get"], url_path="no-leidas")
    def no_leidas(self, request):
        return Response({"no_leidas": Notificacion.objects.filter(usuario=request.user, leida=False, canal="app").count()})


class BitacoraViewSet(viewsets.ReadOnlyModelViewSet):
    """Bitacora de auditoria (RF-51): accesos y acciones sensibles."""
    queryset = BitacoraAuditoria.objects.select_related("usuario").order_by("-fecha")
    serializer_class = BitacoraSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("auditoria.ver")]
    filterset_fields = {"accion": ["exact", "icontains"], "usuario": ["exact"], "entidad": ["exact"], "fecha": ["gte", "lte"]}


class IncidenciaViewSet(PermisosPorAccion, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Cualquier usuario reporta incidencias; quien tiene incidencias.ver las gestiona (RF-50)."""
    serializer_class = IncidenciaSerializer
    http_method_names = ["get", "post", "patch"]
    permisos_por_accion = {"partial_update": [IsAuthenticated, tiene_permiso("incidencias.ver")], "update": [IsAuthenticated, tiene_permiso("incidencias.ver")],
                           "*": [IsAuthenticated]}
    filterset_fields = ["estado", "severidad", "tipo"]

    def get_queryset(self):
        qs = Incidencia.objects.order_by("-fecha_reporte")
        return qs if self.request.user.tiene_permiso("incidencias.ver") else qs.filter(reportada_por=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reportada_por=self.request.user)

    def perform_update(self, serializer):
        cierra = serializer.validated_data.get("estado") in ("resuelta", "descartada")
        serializer.save(**({"fecha_resolucion": timezone.now()} if cierra else {}))


class ConsumoIAViewSet(viewsets.ReadOnlyModelViewSet):
    """Consumo y costo del servicio de IA (RNF-25)."""
    queryset = ConsumoIA.objects.order_by("-fecha")
    serializer_class = ConsumoSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("configuracion.gestionar")]
    filterset_fields = {"funcion": ["exact"], "usuario": ["exact"], "fecha": ["gte", "lte"]}

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    @action(detail=False, methods=["get"])
    def resumen(self, request):
        """Totales por mes y por funcion (tokens, costo estimado y tiempo promedio de respuesta)."""
        filas = (ConsumoIA.objects.annotate(mes=TruncMonth("fecha")).values("mes", "funcion")
                 .annotate(llamadas=Count("id"), tokens_entrada=Sum("tokens_entrada"), tokens_salida=Sum("tokens_salida"), costo=Sum("costo_estimado"))
                 .order_by("-mes", "funcion"))
        return Response([{**f, "costo": float(f["costo"] or 0)} for f in filas])


class ConfiguracionViewSet(viewsets.ModelViewSet):
    """Parametros del sistema sin tocar codigo (RF-49): tamano maximo de archivo, umbral de alertas, etc."""
    queryset = ConfiguracionSistema.objects.order_by("clave")
    serializer_class = ConfiguracionSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("configuracion.gestionar")]
    lookup_field = "clave"
    lookup_value_regex = r"[\w.\-]+"
    http_method_names = ["get", "post", "patch"]
    pagination_class = None

    def perform_create(self, serializer):
        serializer.save(actualizado_por=self.request.user)

    def perform_update(self, serializer):
        serializer.save(actualizado_por=self.request.user)
