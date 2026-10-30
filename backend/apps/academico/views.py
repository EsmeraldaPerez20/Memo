from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permisos import PermisosPorAccion, tiene_permiso
from core.serializadores import crear_serializador

from .models import Materia, Tema, Unidad, UsuarioMateria

MateriaSerializer = crear_serializador(Materia, solo_lectura=("creada_por",))
UnidadSerializer = crear_serializador(Unidad)
TemaSerializer = crear_serializador(Tema)

GESTION = {"*": [IsAuthenticated, tiene_permiso("materias.gestionar")],
           "list": [IsAuthenticated], "retrieve": [IsAuthenticated], "arbol": [IsAuthenticated]}


class MateriaViewSet(PermisosPorAccion, viewsets.ModelViewSet):
    """Catalogo de materias: lo ve todo usuario; lo modifica quien tiene materias.gestionar (RF-48)."""
    queryset = Materia.objects.order_by("nombre")
    serializer_class = MateriaSerializer
    permisos_por_accion = GESTION
    filterset_fields = ["activa"]
    search_fields = ["nombre"]

    def perform_create(self, serializer):
        serializer.save(creada_por=self.request.user)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"])
    def arbol(self, request, pk=None):
        """Materia con sus unidades y temas (los subtemas van anidados en 'subtemas')."""
        materia = self.get_object()
        salida = {"id": materia.id, "nombre": materia.nombre, "unidades": []}
        for u in Unidad.objects.filter(materia=materia).order_by("orden", "id"):
            nodos = {t.id: {"id": t.id, "nombre": t.nombre, "orden": t.orden, "subtemas": []}
                     for t in Tema.objects.filter(unidad=u).order_by("orden", "id")}
            raiz = []
            for t in Tema.objects.filter(unidad=u).order_by("orden", "id"):
                (nodos[t.tema_padre_id]["subtemas"] if t.tema_padre_id in nodos else raiz).append(nodos[t.id])
            salida["unidades"].append({"id": u.id, "nombre": u.nombre, "orden": u.orden, "temas": raiz})
        return Response(salida)


class UnidadViewSet(PermisosPorAccion, viewsets.ModelViewSet):
    queryset = Unidad.objects.order_by("materia", "orden")
    serializer_class = UnidadSerializer
    permisos_por_accion = GESTION
    filterset_fields = ["materia"]


class TemaViewSet(PermisosPorAccion, viewsets.ModelViewSet):
    queryset = Tema.objects.order_by("unidad", "orden")
    serializer_class = TemaSerializer
    permisos_por_accion = GESTION
    filterset_fields = ["unidad", "tema_padre", "unidad__materia"]
    search_fields = ["nombre"]


class MisMateriasView(APIView):
    """Materias que cursa (estudiante) o imparte (docente). El administrador puede asignar a otros usuarios."""

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    def get(self, request):
        filas = UsuarioMateria.objects.filter(usuario=request.user).select_related("materia")
        return Response([{"materia": f.materia_id, "nombre": f.materia.nombre, "relacion": f.relacion, "fecha_alta": f.fecha_alta} for f in filas])

    @extend_schema(request={"application/json": {"type": "object", "properties": {"materia": {"type": "integer"}, "usuario": {"type": "integer"}}}}, responses={200: {"type": "object"}})
    def post(self, request):
        materia = Materia.objects.filter(pk=request.data.get("materia"), activa=True).first()
        if materia is None:
            raise serializers.ValidationError({"materia": "La materia no existe o no esta activa."})
        destino, relacion = request.user, ("imparte" if request.user.es_docente else "cursa")
        if request.user.es_administrador and request.data.get("usuario"):
            from apps.usuarios.models import Usuario
            destino = Usuario.objects.filter(pk=request.data["usuario"]).first()
            if destino is None:
                raise serializers.ValidationError({"usuario": "El usuario no existe."})
            relacion = request.data.get("relacion") or ("imparte" if destino.es_docente else "cursa")
            if relacion not in ("cursa", "imparte"):
                raise serializers.ValidationError({"relacion": "Debe ser 'cursa' o 'imparte'."})
        if UsuarioMateria.objects.filter(usuario=destino, materia=materia, relacion=relacion).exists():
            return Response({"detail": "Ya estaba asignada."}, status=status.HTTP_200_OK)
        UsuarioMateria.objects.create(usuario=destino, materia=materia, relacion=relacion)
        return Response({"materia": materia.id, "nombre": materia.nombre, "relacion": relacion}, status=status.HTTP_201_CREATED)


class MiMateriaDetalleView(APIView):
    @extend_schema(responses={204: None})
    def delete(self, request, materia_id):
        UsuarioMateria.objects.filter(usuario=request.user, materia_id=materia_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
