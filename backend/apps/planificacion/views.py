from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permisos import EsPersonalAcademico
from core.serializadores import crear_serializador
from core.viewsets import DuenioMixin
from servicios import recomendaciones

from .models import Meta, PlanEstudio, PlanEstudioItem, Recomendacion, Tarea

RecomendacionSerializer = crear_serializador(
    Recomendacion, "RecomendacionSerializer", solo_lectura=("usuario", "tema", "titulo", "tipo", "prioridad", "origen", "fecha_respuesta"))
PlanItemSerializer = crear_serializador(PlanEstudioItem, "PlanItemSerializer", solo_lectura=("plan", "recomendacion", "fecha_completado"))
MetaSerializer = crear_serializador(Meta, "MetaSerializer", solo_lectura=("usuario", "valor_actual"))
TareaSerializer = crear_serializador(Tarea, "TareaSerializer", solo_lectura=("usuario", "fecha_completada"))
_PlanBase = crear_serializador(PlanEstudio, "PlanBase", solo_lectura=("usuario", "revisado_por", "generado_por_ia"))


class PlanEstudioSerializer(_PlanBase):
    items = serializers.SerializerMethodField()

    def get_items(self, plan):
        return PlanItemSerializer(PlanEstudioItem.objects.filter(plan=plan).order_by("orden"), many=True).data


class RecomendacionViewSet(DuenioMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Recomendaciones personalizadas (RF-37). El estudiante las acepta, modifica o rechaza con PATCH {estado} (RF-39)."""
    queryset = Recomendacion.objects.select_related("tema").order_by("-fecha_creacion")
    serializer_class = RecomendacionSerializer
    http_method_names = ["get", "post", "patch"]
    filterset_fields = ["estado", "tipo", "tema", "prioridad"]

    def perform_update(self, serializer):
        antes = serializer.instance.estado
        extra = {"fecha_respuesta": timezone.now()} if serializer.validated_data.get("estado", antes) != antes else {}
        serializer.save(**extra)

    @extend_schema(request=None, responses={201: RecomendacionSerializer(many=True)})
    @action(detail=False, methods=["post"])
    def generar(self, request):
        """Crea recomendaciones a partir de las dificultades activas del estudiante."""
        creadas = recomendaciones.generar_recomendaciones(request.user)
        return Response(RecomendacionSerializer(creadas, many=True).data, status=201)


class PlanEstudioViewSet(DuenioMixin, viewsets.ModelViewSet):
    """Rutas de aprendizaje y planes semanales (RF-38, RF-40)."""
    queryset = PlanEstudio.objects.order_by("-fecha_creacion")
    serializer_class = PlanEstudioSerializer
    filterset_fields = ["tipo", "estado"]

    def get_queryset(self):
        if self.action == "revisar":                     # el docente revisa planes de sus estudiantes
            return PlanEstudio.objects.all()
        return super().get_queryset()

    @extend_schema(request={"application/json": {"type": "object", "properties": {"tipo": {"type": "string"}, "dias": {"type": "integer"}}}},
                   responses={201: PlanEstudioSerializer})
    @action(detail=False, methods=["post"])
    def generar(self, request):
        """Arma un plan propuesto con las recomendaciones pendientes o aceptadas."""
        tipo = request.data.get("tipo", "semanal")
        if tipo not in ("semanal", "ruta"):
            raise serializers.ValidationError({"tipo": "Usa 'semanal' o 'ruta'."})
        try:
            plan = recomendaciones.generar_plan(request.user, tipo, int(request.data.get("dias", 7)))
        except ValueError as e:
            raise serializers.ValidationError({"detail": str(e)})
        return Response(PlanEstudioSerializer(plan).data, status=201)

    @extend_schema(request=PlanItemSerializer, responses=PlanItemSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def items(self, request, pk=None):
        plan = self.get_object()
        if request.method == "POST":
            s = PlanItemSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            s.save(plan=plan)
        return Response(PlanItemSerializer(PlanEstudioItem.objects.filter(plan=plan).order_by("orden"), many=True).data)

    @extend_schema(request={"application/json": {"type": "object", "properties": {"estado": {"type": "string"}}}}, responses=PlanEstudioSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, EsPersonalAcademico])
    def revisar(self, request, pk=None):
        """El docente deja constancia de que reviso el plan (y opcionalmente cambia su estado)."""
        plan = self.get_object()
        plan.revisado_por = request.user
        if request.data.get("estado") in ("propuesto", "activo", "modificado", "finalizado", "descartado"):
            plan.estado = request.data["estado"]
        plan.save()
        return Response(PlanEstudioSerializer(plan).data)


class PlanItemViewSet(DuenioMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    campo_usuario = "plan__usuario"
    queryset = PlanEstudioItem.objects.select_related("plan").order_by("plan", "orden")
    serializer_class = PlanItemSerializer
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        if "completado" in serializer.validated_data:
            serializer.save(fecha_completado=timezone.now() if serializer.validated_data["completado"] else None)
        else:
            serializer.save()


class MetaViewSet(DuenioMixin, viewsets.ModelViewSet):
    """Metas medibles (RF-41). El avance (valor_actual) lo calcula el sistema al terminar actividades."""
    queryset = Meta.objects.order_by("-fecha_creacion")
    serializer_class = MetaSerializer
    filterset_fields = ["estado", "indicador", "materia"]


class TareaViewSet(DuenioMixin, viewsets.ModelViewSet):
    """Pendientes y recordatorios de la pantalla de inicio (RF-42, RF-54)."""
    queryset = Tarea.objects.select_related("materia").order_by("completada", "fecha_limite")
    serializer_class = TareaSerializer
    filterset_fields = ["completada", "tipo", "materia"]
    ordering_fields = ["fecha_limite"]

    def perform_update(self, serializer):
        if "completada" in serializer.validated_data:
            serializer.save(fecha_completada=timezone.now() if serializer.validated_data["completada"] else None)
        else:
            serializer.save()
