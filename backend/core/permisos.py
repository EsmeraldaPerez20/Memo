"""Permisos basados en las tablas roles / permisos / roles_permisos (no en los grupos de Django)."""
from rest_framework.permissions import BasePermission, IsAuthenticated


def tiene_permiso(codigo):
    """Clase de permiso DRF: exige que el rol del usuario tenga el permiso 'codigo'."""
    class _Permiso(BasePermission):
        message = f"Se requiere el permiso '{codigo}'."

        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and u.tiene_permiso(codigo))

    _Permiso.__name__ = "Permiso_" + codigo.replace(".", "_")
    return _Permiso


def es_rol(*roles):
    class _Rol(BasePermission):
        message = "Tu rol no tiene acceso a este recurso."

        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and u.rol.nombre in roles)

    _Rol.__name__ = "Rol_" + "_".join(roles)
    return _Rol


EsPersonalAcademico = es_rol("docente", "administrador")
EsEstudiante = es_rol("estudiante")


class PermisosPorAccion:
    """Permite declarar permisos distintos por accion: {'create': [...], '*': [...]}."""
    permisos_por_accion = {}

    def get_permissions(self):
        clases = self.permisos_por_accion.get(getattr(self, "action", None)) or self.permisos_por_accion.get("*") \
            or self.permission_classes or [IsAuthenticated]
        return [c() for c in clases]
