import io

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.academico.models import Tema, UsuarioMateria
from core.auditoria import registrar
from core.permisos import PermisosPorAccion, tiene_permiso
from core.viewsets import DuenioMixin
from servicios import almacenamiento, notificaciones, rag
from servicios.almacenamiento import AlmacenamientoError
from servicios.texto import ErrorExtraccion

from .models import Documento, DocumentoTema, ElementoDocumento, Material
from .serializers import (EXTENSIONES, DocumentoSerializer, ElementoSerializer, MaterialSerializer, SubirDocumentoSerializer,
                          SubirMaterialSerializer)

PARSERS = [MultiPartParser, FormParser, JSONParser]


def _guardar(usuario, archivo):
    tipo = EXTENSIONES[archivo.name.rsplit(".", 1)[-1].lower()]
    ruta = almacenamiento.ruta_nueva(usuario.id, archivo.name)
    almacenamiento.guardar(ruta, archivo.read(), archivo.content_type or "application/octet-stream")
    return ruta, tipo, archivo.size


def _enlace(request, ruta, nombre_url, pk):
    url = almacenamiento.url_temporal(ruta, 300)
    return Response({"url": url or request.build_absolute_uri(reverse(nombre_url, args=[pk])), "expira_en_segundos": 300 if url else None})


def _descarga(ruta, nombre):
    return FileResponse(io.BytesIO(almacenamiento.leer(ruta)), as_attachment=True, filename=nombre)


class DocumentoViewSet(DuenioMixin, viewsets.ModelViewSet):
    """Apuntes privados del estudiante (RF-13 a RF-20): solo su dueño los ve y el tutor los usa para responderle."""
    queryset = Documento.objects.filter(fecha_eliminacion__isnull=True).select_related("materia").order_by("-fecha_subida")
    serializer_class = DocumentoSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("documentos.subir")]
    parser_classes = PARSERS
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ["materia", "estado_analisis", "tipo_archivo"]
    search_fields = ["nombre"]

    @extend_schema(request={"multipart/form-data": SubirDocumentoSerializer}, responses={201: DocumentoSerializer})
    def create(self, request, *args, **kwargs):
        s = SubirDocumentoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        f, materia = s.validated_data["archivo"], s.validated_data.get("materia")
        try:
            ruta, tipo, tam = _guardar(request.user, f)
        except AlmacenamientoError as e:
            return Response({"detail": str(e)}, status=502)
        doc = Documento.objects.create(usuario=request.user, materia=materia, nombre=f.name[:255], archivo_url=ruta, tipo_archivo=tipo, tamano_bytes=tam)
        registrar(request, "subir_documento", entidad="documentos", entidad_id=doc.id)
        error = None
        if s.validated_data["analizar"]:
            try:
                rag.indexar_documento(doc, request.user)
            except (ErrorExtraccion, AlmacenamientoError) as e:
                error = str(e)
        datos = DocumentoSerializer(doc).data
        if error:
            datos["analisis_error"] = error
        return Response(datos, status=201)

    def destroy(self, request, *args, **kwargs):
        """RF-20: borra el archivo y marca el documento como eliminado (un trigger borra sus fragmentos)."""
        doc = self.get_object()
        try:
            almacenamiento.eliminar(doc.archivo_url)
        except AlmacenamientoError as e:
            return Response({"detail": str(e)}, status=502)
        doc.fecha_eliminacion = timezone.now()
        doc.save(update_fields=["fecha_eliminacion"])
        registrar(request, "eliminar_documento", entidad="documentos", entidad_id=doc.id)
        return Response(status=204)

    @extend_schema(request=None, responses={200: {"type": "object"}})
    @action(detail=True, methods=["post"], throttle_scope="ia")
    def analizar(self, request, pk=None):
        """Extrae el texto, genera fragmentos con embeddings y el analisis (resumen, conceptos, preguntas...)."""
        doc = self.get_object()
        try:
            n = rag.indexar_documento(doc, request.user)
        except (ErrorExtraccion, AlmacenamientoError) as e:
            return Response({"detail": str(e), "estado_analisis": doc.estado_analisis}, status=422)
        return Response({"fragmentos": n, "estado_analisis": doc.estado_analisis})

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"])
    def elementos(self, request, pk=None):
        """Resultado del analisis agrupado por tipo (RF-16)."""
        salida = {}
        for e in ElementoDocumento.objects.filter(documento=self.get_object()).order_by("id"):
            salida.setdefault(e.tipo, []).append(ElementoSerializer(e).data)
        return Response(salida)

    @extend_schema(request={"application/json": {"type": "object", "properties": {
        "materia": {"type": "integer"}, "temas": {"type": "array", "items": {"type": "integer"}}}}})
    @action(detail=True, methods=["get", "post"])
    def temas(self, request, pk=None):
        """GET: temas sugeridos por la IA. POST: el estudiante confirma materia y temas (RF-18)."""
        doc = self.get_object()
        if request.method == "POST":
            ids = [int(i) for i in request.data.get("temas", [])]
            with transaction.atomic():
                if request.data.get("materia"):
                    doc.materia_id = request.data["materia"]
                    doc.save(update_fields=["materia"])
                DocumentoTema.objects.filter(documento=doc, sugerido_por_ia=True, confirmado=False).exclude(tema_id__in=ids).delete()
                for t in Tema.objects.filter(id__in=ids):
                    if DocumentoTema.objects.filter(documento=doc, tema=t).exists():
                        DocumentoTema.objects.filter(documento=doc, tema=t).update(confirmado=True)
                    else:
                        DocumentoTema.objects.create(documento=doc, tema=t, sugerido_por_ia=False, confirmado=True)
        return Response([{"tema": x.tema_id, "nombre": x.tema.nombre, "sugerido_por_ia": x.sugerido_por_ia, "confirmado": x.confirmado}
                         for x in DocumentoTema.objects.filter(documento=doc).select_related("tema")])

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"])
    def enlace(self, request, pk=None):
        """Enlace temporal para ver el archivo (RF-19): el archivo nunca es publico."""
        return _enlace(request, self.get_object().archivo_url, "documento-descargar", pk)

    @extend_schema(responses={200: {"type": "string", "format": "binary"}})
    @action(detail=True, methods=["get"])
    def descargar(self, request, pk=None):
        doc = self.get_object()
        return _descarga(doc.archivo_url, doc.nombre)


class MaterialViewSet(PermisosPorAccion, viewsets.ModelViewSet):
    """Materiales del docente (RF-46, RF-47): el estudiante solo ve los aprobados de las materias que cursa."""
    serializer_class = MaterialSerializer
    parser_classes = PARSERS
    http_method_names = ["get", "post", "patch", "delete"]
    filterset_fields = ["materia", "tema", "estado"]
    search_fields = ["titulo", "descripcion"]
    permisos_por_accion = {
        "list": [IsAuthenticated], "retrieve": [IsAuthenticated], "enlace": [IsAuthenticated], "descargar": [IsAuthenticated],
        "aprobar": [IsAuthenticated, tiene_permiso("materiales.aprobar")], "rechazar": [IsAuthenticated, tiene_permiso("materiales.aprobar")],
        "*": [IsAuthenticated, tiene_permiso("materiales.gestionar")],
    }

    def get_queryset(self):
        u = self.request.user
        qs = Material.objects.select_related("materia").order_by("-fecha_subida")
        if u.es_administrador or u.tiene_permiso("materiales.aprobar"):
            return qs
        if u.tiene_permiso("materiales.gestionar"):
            imparte = list(UsuarioMateria.objects.filter(usuario=u, relacion="imparte").values_list("materia_id", flat=True))
            return qs.filter(Q(subido_por=u) | Q(estado="aprobado", materia_id__in=imparte))
        cursa = list(UsuarioMateria.objects.filter(usuario=u, relacion="cursa").values_list("materia_id", flat=True))
        return qs.filter(estado="aprobado", materia_id__in=cursa)

    def _solo_autor(self, obj):
        if obj.subido_por_id != self.request.user.id and not self.request.user.es_administrador:
            raise PermissionDenied("Solo quien subio el material puede modificarlo.")
        return obj

    def get_object(self):
        obj = super().get_object()
        return self._solo_autor(obj) if self.action in ("partial_update", "destroy") else obj

    @extend_schema(request={"multipart/form-data": SubirMaterialSerializer}, responses={201: MaterialSerializer})
    def create(self, request, *args, **kwargs):
        s = SubirMaterialSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if not request.user.es_administrador and not UsuarioMateria.objects.filter(usuario=request.user, materia=d["materia"], relacion="imparte").exists():
            raise PermissionDenied("Solo puedes subir materiales a las materias que impartes.")
        try:
            ruta, tipo, tam = _guardar(request.user, d["archivo"])
        except AlmacenamientoError as e:
            return Response({"detail": str(e)}, status=502)
        m = Material.objects.create(materia=d["materia"], tema=d.get("tema"), titulo=d["titulo"], descripcion=d.get("descripcion") or None,
                                    archivo_url=ruta, tipo_archivo=tipo, tamano_bytes=tam, subido_por=request.user)
        registrar(request, "subir_material", entidad="materiales", entidad_id=m.id)
        return Response(MaterialSerializer(m).data, status=201)

    def destroy(self, request, *args, **kwargs):
        m = self.get_object()
        try:
            almacenamiento.eliminar(m.archivo_url)
        except AlmacenamientoError as e:
            return Response({"detail": str(e)}, status=502)
        material_id = m.id
        m.delete()          # la base borra sus fragmentos en cascada
        registrar(request, "eliminar_material", entidad="materiales", entidad_id=material_id)
        return Response(status=204)

    @extend_schema(request={"application/json": {"type": "object", "properties": {"comentarios": {"type": "string"}}}}, responses=MaterialSerializer)
    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba el material y lo indexa para que el tutor lo use (RF-47). Solo los aprobados llegan a los estudiantes."""
        m = self.get_object()
        if m.estado == "aprobado":
            return Response(MaterialSerializer(m).data)
        ahora = timezone.now()
        try:
            with transaction.atomic():
                m.estado, m.revisado_por, m.fecha_revision, m.fecha_publicacion = "aprobado", request.user, ahora, ahora
                m.comentarios_revision = request.data.get("comentarios") or None
                m.save()
                rag.indexar_material(m, request.user)
        except (ErrorExtraccion, AlmacenamientoError) as e:
            return Response({"detail": f"No se pudo aprobar el material: {e}"}, status=422)
        registrar(request, "aprobar_material", entidad="materiales", entidad_id=m.id)
        for fila in UsuarioMateria.objects.filter(materia=m.materia, relacion="cursa").select_related("usuario"):
            notificaciones.notificar(fila.usuario, "material", f"Nuevo material en {m.materia.nombre}", m.titulo)
        return Response(MaterialSerializer(m).data)

    @extend_schema(request={"application/json": {"type": "object", "properties": {"comentarios": {"type": "string"}}}}, responses=MaterialSerializer)
    @action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        m = self.get_object()
        comentarios = str(request.data.get("comentarios", "")).strip()
        if not comentarios:
            raise serializers.ValidationError({"comentarios": "Indica el motivo del rechazo."})
        m.estado, m.revisado_por, m.fecha_revision, m.comentarios_revision = "rechazado", request.user, timezone.now(), comentarios
        m.fecha_publicacion = None
        m.save()
        registrar(request, "rechazar_material", entidad="materiales", entidad_id=m.id)
        notificaciones.notificar(m.subido_por, "material", f"Material rechazado: {m.titulo}", comentarios)
        return Response(MaterialSerializer(m).data)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"])
    def enlace(self, request, pk=None):
        return _enlace(request, self.get_object().archivo_url, "material-descargar", pk)

    @extend_schema(responses={200: {"type": "string", "format": "binary"}})
    @action(detail=True, methods=["get"])
    def descargar(self, request, pk=None):
        m = self.get_object()
        return _descarga(m.archivo_url, m.titulo)
