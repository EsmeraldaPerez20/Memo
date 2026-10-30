import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.auditoria import registrar
from core.permisos import PermisosPorAccion, tiene_permiso
from servicios import configuracion

from .models import PerfilAcademico, Permiso, PreferenciaUsuario, Rol, RolPermiso, TokenRecuperacion, Usuario
from .serializers import (ActualizarYoSerializer, LoginSerializer, PerfilSerializer, PermisoSerializer, PreferenciasSerializer,
                          RegistroSerializer, RolSerializer, UsuarioAdminSerializer, UsuarioSerializer, hash_token)


def _tokens(usuario):
    refresh = RefreshToken.for_user(usuario)
    refresh["rol"], refresh["nombre"] = usuario.rol.nombre, usuario.get_full_name()
    return {"access": str(refresh.access_token), "refresh": str(refresh), "usuario": UsuarioSerializer(usuario).data}


class _Publica(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    """POST: correo + password -> access, refresh y datos del usuario."""
    throttle_scope = "auth"
    serializer_class = LoginSerializer


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class RegistroView(_Publica):
    @extend_schema(request=RegistroSerializer, responses={201: UsuarioSerializer})
    def post(self, request):
        s = RegistroSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        usuario = s.save()
        registrar(request, "registro", usuario=usuario)
        return Response(_tokens(usuario), status=status.HTTP_201_CREATED)


class GoogleLoginView(_Publica):
    """Inicio de sesion con Google: el frontend envia el id_token que entrega Google Identity Services."""
    @extend_schema(request={"application/json": {"type": "object", "properties": {"id_token": {"type": "string"}, "acepta_aviso": {"type": "boolean"}}}}, responses={200: {"type": "object"}})
    def post(self, request):
        if not settings.GOOGLE_CLIENT_ID:
            return Response({"detail": "El inicio de sesion con Google no esta configurado (GOOGLE_CLIENT_ID)."}, status=503)
        try:
            from google.auth.transport import requests as greq
            from google.oauth2 import id_token
            info = id_token.verify_oauth2_token(request.data.get("id_token", ""), greq.Request(), settings.GOOGLE_CLIENT_ID)
        except Exception:
            return Response({"detail": "Credencial de Google invalida."}, status=400)
        if not info.get("email_verified"):
            return Response({"detail": "Tu correo de Google no esta verificado."}, status=400)
        usuario = Usuario.objects.filter(google_id=info["sub"]).first() or Usuario.objects.filter(correo__iexact=info["email"]).first()
        if usuario is None:
            if not request.data.get("acepta_aviso"):
                return Response({"detail": "Debes aceptar el aviso de privacidad para crear tu cuenta.", "codigo": "aviso_requerido"}, status=400)
            with transaction.atomic():
                usuario = Usuario.objects.create_user(
                    info["email"], info.get("given_name") or info.get("name") or info["email"], None, google_id=info["sub"],
                    apellido=info.get("family_name"), aviso_privacidad_version=request.data.get("version_aviso", "1.0"),
                    aviso_privacidad_aceptado_en=timezone.now())
                PerfilAcademico.objects.create(usuario=usuario)
                PreferenciaUsuario.objects.create(usuario=usuario)
        elif not usuario.google_id:
            usuario.google_id = info["sub"]
            usuario.save(update_fields=["google_id"])
        if not usuario.is_active:
            return Response({"detail": "Tu cuenta esta desactivada."}, status=403)
        registrar(request, "login_google", usuario=usuario)
        return Response(_tokens(usuario))


class RecuperarView(_Publica):
    """RF-04: siempre responde igual, exista o no el correo (no revela que cuentas existen)."""
    @extend_schema(request={"application/json": {"type": "object", "properties": {"correo": {"type": "string"}}}}, responses={200: {"type": "object"}})
    def post(self, request):
        usuario = Usuario.objects.filter(correo__iexact=str(request.data.get("correo", "")).strip(), is_active=True).first()
        if usuario:
            token = secrets.token_urlsafe(32)
            minutos = int(configuracion.obtener("vigencia_token_recuperacion_min", 30))
            TokenRecuperacion.objects.create(usuario=usuario, token_hash=hash_token(token), expira_en=timezone.now() + timedelta(minutes=minutos))
            enlace = f"{settings.FRONTEND_URL}/restablecer?token={token}"
            send_mail("Restablece tu contrasena de Memo",
                      f"Hola {usuario.nombre},\n\nUsa este enlace para crear una nueva contrasena (vale {minutos} minutos):\n{enlace}\n\n"
                      "Si no lo pediste tu, ignora este correo.", None, [usuario.correo])
            registrar(request, "recuperacion_solicitada", usuario=usuario)
        return Response({"detail": "Si el correo existe, enviamos las instrucciones para restablecer la contrasena."})


class RestablecerView(_Publica):
    @extend_schema(request={"application/json": {"type": "object", "properties": {"token": {"type": "string"}, "password": {"type": "string"}}}}, responses={200: {"type": "object"}})
    def post(self, request):
        invalido = Response({"detail": "El enlace no es valido o ya expiro. Solicita uno nuevo."}, status=400)
        fila = TokenRecuperacion.objects.filter(token_hash=hash_token(str(request.data.get("token", ""))), usado=False,
                                                expira_en__gt=timezone.now()).select_related("usuario").first()
        if fila is None:
            return invalido
        try:
            validate_password(request.data.get("password", ""), fila.usuario)
        except DjangoValidationError as e:
            return Response({"password": list(e.messages)}, status=400)
        with transaction.atomic():
            fila.usuario.set_password(request.data["password"])
            fila.usuario.save(update_fields=["password"])
            TokenRecuperacion.objects.filter(usuario=fila.usuario, usado=False).update(usado=True)
        registrar(request, "password_restablecida", usuario=fila.usuario)
        return Response({"detail": "Contrasena actualizada. Ya puedes iniciar sesion."})


class YoView(APIView):
    """GET: mi cuenta. PATCH: nombre, apellido, telefono."""
    @extend_schema(responses=UsuarioSerializer)
    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

    @extend_schema(request=ActualizarYoSerializer, responses=UsuarioSerializer)
    def patch(self, request):
        s = ActualizarYoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(request.user, k, v or None if k in ("apellido", "telefono") else v)
        request.user.save()
        return Response(UsuarioSerializer(request.user).data)


class PerfilView(RetrieveUpdateAPIView):
    """Perfil academico del estudiante (RF-05)."""
    serializer_class = PerfilSerializer
    http_method_names = ["get", "patch", "put"]

    def get_object(self):
        return PerfilAcademico.objects.filter(usuario=self.request.user).first() or PerfilAcademico.objects.create(usuario=self.request.user)


class PreferenciasView(RetrieveUpdateAPIView):
    """Accesibilidad y notificaciones (RNF-19, RF-54)."""
    serializer_class = PreferenciasSerializer
    http_method_names = ["get", "patch", "put"]

    def get_object(self):
        return PreferenciaUsuario.objects.filter(usuario=self.request.user).first() or PreferenciaUsuario.objects.create(usuario=self.request.user)


class UsuarioAdminViewSet(viewsets.ModelViewSet):
    """Administracion de usuarios (permiso usuarios.gestionar)."""
    queryset = Usuario.objects.select_related("rol").order_by("id")
    serializer_class = UsuarioAdminSerializer
    permission_classes = [IsAuthenticated, tiene_permiso("usuarios.gestionar")]
    filterset_fields = ["rol", "is_active"]
    search_fields = ["nombre", "apellido", "correo"]
    http_method_names = ["get", "post", "patch", "delete"]

    def perform_update(self, serializer):
        rol_anterior = serializer.instance.rol_id
        usuario = serializer.save()
        if usuario.rol_id != rol_anterior:
            registrar(self.request, "cambio_rol", entidad="usuarios", entidad_id=usuario.id,
                      detalle={"rol_anterior": rol_anterior, "rol_nuevo": usuario.rol_id})

    def perform_create(self, serializer):
        usuario = serializer.save()
        registrar(self.request, "crear_usuario", entidad="usuarios", entidad_id=usuario.id)


class RolViewSet(PermisosPorAccion, viewsets.ReadOnlyModelViewSet):
    queryset = Rol.objects.order_by("id")
    serializer_class = RolSerializer
    pagination_class = None
    permisos_por_accion = {"*": [IsAuthenticated, tiene_permiso("usuarios.gestionar")]}

    @extend_schema(request={"application/json": {"type": "object", "properties": {"permisos": {"type": "array", "items": {"type": "string"}}}}},
                   responses=RolSerializer)
    @action(detail=True, methods=["put"], url_path="permisos")
    def asignar_permisos(self, request, pk=None):
        """Reemplaza los permisos del rol por la lista de codigos recibida."""
        rol = self.get_object()
        codigos = request.data.get("permisos", [])
        permisos = list(Permiso.objects.filter(codigo__in=codigos))
        if len(permisos) != len(set(codigos)):
            raise serializers.ValidationError({"permisos": "Alguno de los codigos no existe."})
        with transaction.atomic():
            RolPermiso.objects.filter(rol=rol).delete()
            RolPermiso.objects.bulk_create([RolPermiso(rol=rol, permiso=p) for p in permisos])
        registrar(request, "cambio_permisos_rol", entidad="roles", entidad_id=rol.id, detalle={"permisos": sorted(codigos)})
        return Response(RolSerializer(rol).data)


class PermisoViewSet(PermisosPorAccion, viewsets.ReadOnlyModelViewSet):
    queryset = Permiso.objects.order_by("codigo")
    serializer_class = PermisoSerializer
    pagination_class = None
    permisos_por_accion = {"*": [IsAuthenticated, tiene_permiso("usuarios.gestionar")]}
