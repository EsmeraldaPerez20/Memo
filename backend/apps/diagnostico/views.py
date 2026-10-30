from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academico.models import Materia, UsuarioMateria
from core.auditoria import registrar
from core.permisos import tiene_permiso
from core.serializadores import crear_serializador
from core.viewsets import DuenioMixin
from servicios import dashboard

from .models import Dificultad, DificultadEvidencia, Progreso

ProgresoSerializer = crear_serializador(
    Progreso, "ProgresoSerializer", solo_lectura=("usuario",),
    extra={"tema_nombre": serializers.CharField(source="tema.nombre", read_only=True),
           "materia": serializers.IntegerField(source="tema.unidad.materia_id", read_only=True)})
DificultadSerializer = crear_serializador(
    Dificultad, "DificultadSerializer", solo_lectura=("usuario",),
    extra={"tema_nombre": serializers.CharField(source="tema.nombre", read_only=True)})


class ProgresoViewSet(DuenioMixin, viewsets.ReadOnlyModelViewSet):
    """Nivel de dominio por tema (RF-25, RF-43), calculado por el Knowledge Tracing al terminar cada actividad."""
    queryset = Progreso.objects.select_related("tema__unidad").order_by("-fecha_actualizacion")
    serializer_class = ProgresoSerializer
    filterset_fields = ["tema", "nivel_dominio", "tema__unidad__materia"]


class DificultadViewSet(DuenioMixin, viewsets.ReadOnlyModelViewSet):
    """Dificultades detectadas (RF-21 a RF-24)."""
    queryset = Dificultad.objects.select_related("tema").order_by("-fecha_deteccion")
    serializer_class = DificultadSerializer
    filterset_fields = ["estado", "nivel", "tema"]

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    @action(detail=True, methods=["get"])
    def evidencias(self, request, pk=None):
        """Respuestas que originaron la dificultad (RF-24)."""
        filas = DificultadEvidencia.objects.filter(dificultad=self.get_object()).select_related("respuesta__pregunta")
        return Response([{"pregunta": f.respuesta.pregunta.enunciado, "respuesta_usuario": f.respuesta.respuesta_usuario,
                          "retroalimentacion": f.respuesta.retroalimentacion} for f in filas])


class DashboardView(APIView):
    """Resumen del estudiante: indicadores, avance por materia, dificultades, pendientes y metas (RF-42, RF-43)."""
    permission_classes = [IsAuthenticated, tiene_permiso("dashboard.ver")]

    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request):
        return Response(dashboard.resumen(request.user))


class ExportarReporteView(APIView):
    """Descarga el reporte en Excel o PDF (RF-45)."""
    permission_classes = [IsAuthenticated, tiene_permiso("reportes.exportar")]

    @extend_schema(responses={200: {"type": "string", "format": "binary"}})
    def get(self, request):
        formato = request.query_params.get("formato", "excel")
        if formato == "excel":
            datos, tipo, nombre = dashboard.a_excel(request.user), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "reporte_memo.xlsx"
        elif formato == "pdf":
            datos, tipo, nombre = dashboard.a_pdf(request.user), "application/pdf", "reporte_memo.pdf"
        else:
            raise serializers.ValidationError({"formato": "Usa 'excel' o 'pdf'."})
        registrar(request, "exportar_reporte", detalle={"formato": formato})
        resp = HttpResponse(datos, content_type=tipo)
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return resp


class DocenteEstudiantesView(APIView):
    """Progreso de los estudiantes de las materias que imparte el docente (permiso estudiantes.ver_progreso)."""
    permission_classes = [IsAuthenticated, tiene_permiso("estudiantes.ver_progreso")]

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    def get(self, request):
        u = request.user
        materias = Materia.objects.all() if u.es_administrador else Materia.objects.filter(
            id__in=UsuarioMateria.objects.filter(usuario=u, relacion="imparte").values("materia_id"))
        if request.query_params.get("materia"):
            materias = materias.filter(pk=request.query_params["materia"])
        salida = []
        for m in materias:
            filas = []
            for em in UsuarioMateria.objects.filter(materia=m, relacion="cursa").select_related("usuario"):
                agg = Progreso.objects.filter(usuario=em.usuario, tema__unidad__materia=m).aggregate(
                    promedio=Avg("porcentaje"), dominados=Count("id", filter=Q(nivel_dominio__in=("alto", "dominado"))), temas=Count("id"))
                filas.append({"usuario": em.usuario_id, "nombre": em.usuario.get_full_name(),
                              "avance_promedio": float(agg["promedio"]) if agg["promedio"] is not None else None,
                              "temas_dominados": agg["dominados"], "temas_con_actividad": agg["temas"],
                              "dificultades_activas": Dificultad.objects.filter(usuario=em.usuario, estado="activa", tema__unidad__materia=m).count()})
            salida.append({"materia": m.id, "nombre": m.nombre, "estudiantes": filas})
        return Response(salida)
