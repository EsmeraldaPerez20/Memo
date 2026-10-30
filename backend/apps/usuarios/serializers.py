import hashlib

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.auditoria import registrar
from core.serializadores import crear_serializador

from .models import Permiso, PerfilAcademico, PreferenciaUsuario, Rol, Usuario

TELEFONO = r"^\+[1-9][0-9]{7,14}$"       # formato internacional: +525512345678

PerfilSerializer = crear_serializador(PerfilAcademico, "PerfilSerializer", excluir=("usuario",))
PreferenciasSerializer = crear_serializador(PreferenciaUsuario, "PreferenciasSerializer", excluir=("usuario",))


class UsuarioSerializer(serializers.ModelSerializer):
    """Datos del usuario autenticado (lo que necesita el frontend para pintar menus segun el rol)."""
    rol = serializers.CharField(source="rol.nombre", read_only=True)
    permisos = serializers.SerializerMethodField()
    perfil = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ["id", "nombre", "apellido", "correo", "telefono", "rol", "permisos", "perfil", "fecha_registro"]
        read_only_fields = fields

    def get_permisos(self, u):
        return sorted(u.permisos_codigos())

    def get_perfil(self, u):
        p = PerfilAcademico.objects.filter(usuario=u).first()
        return PerfilSerializer(p).data if p else None


class LoginSerializer(TokenObtainPairSerializer):
    """Login por correo y contrasena (RF-02). Registra accesos exitosos y fallidos en la bitacora (RF-51)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = user.rol.nombre
        token["nombre"] = user.get_full_name()
        return token

    def validate(self, attrs):
        request = self.context.get("request")
        try:
            datos = super().validate(attrs)
        except Exception:
            registrar(request, "login_fallido", detalle={"correo": str(attrs.get(self.username_field, ""))[:150]})
            raise
        registrar(request, "login", usuario=self.user)
        datos["usuario"] = UsuarioSerializer(self.user).data
        return datos


class RegistroSerializer(serializers.Serializer):
    """Registro de estudiantes (RF-01). Solo exige nombre, correo y contrasena; acepta el aviso de privacidad (RNF-05)."""
    nombre = serializers.CharField(max_length=100)
    apellido = serializers.CharField(max_length=100, required=False, allow_blank=True)
    correo = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    telefono = serializers.RegexField(TELEFONO, required=False, allow_blank=True,
                                      error_messages={"invalid": "Usa el formato internacional, por ejemplo +525512345678."})
    carrera = serializers.CharField(max_length=150, required=False, allow_blank=True)
    semestre = serializers.IntegerField(min_value=1, max_value=15, required=False, allow_null=True)
    nivel_academico = serializers.ChoiceField(choices=["basico", "intermedio", "avanzado"], default="basico")
    acepta_aviso = serializers.BooleanField()
    version_aviso = serializers.CharField(max_length=20, default="1.0")

    def validate_correo(self, v):
        if Usuario.objects.filter(correo__iexact=v.strip()).exists():
            raise serializers.ValidationError("Ya existe una cuenta con ese correo.")
        return v.strip()

    def validate_password(self, v):
        validate_password(v)
        return v

    def validate_acepta_aviso(self, v):
        if not v:
            raise serializers.ValidationError("Debes aceptar el aviso de privacidad para crear tu cuenta.")
        return v

    @transaction.atomic
    def create(self, d):
        usuario = Usuario.objects.create_user(
            d["correo"], d["nombre"], d["password"], apellido=d.get("apellido") or None, telefono=d.get("telefono") or None,
            aviso_privacidad_version=d["version_aviso"], aviso_privacidad_aceptado_en=timezone.now())
        PerfilAcademico.objects.create(usuario=usuario, carrera=d.get("carrera") or None, semestre=d.get("semestre"),
                                       nivel_academico=d["nivel_academico"])
        PreferenciaUsuario.objects.create(usuario=usuario)
        return usuario


class ActualizarYoSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=100, required=False)
    apellido = serializers.CharField(max_length=100, required=False, allow_blank=True)
    telefono = serializers.RegexField(TELEFONO, required=False, allow_null=True, allow_blank=True)


class UsuarioAdminSerializer(serializers.ModelSerializer):
    """Gestion de usuarios por el administrador (RF-49)."""
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = Usuario
        fields = ["id", "nombre", "apellido", "correo", "telefono", "rol", "is_active", "password", "last_login", "fecha_registro"]
        read_only_fields = ["last_login", "fecha_registro"]

    def validate_password(self, v):
        validate_password(v)
        return v

    def validate_correo(self, v):
        existente = Usuario.objects.filter(correo__iexact=v.strip())
        if self.instance:
            existente = existente.exclude(pk=self.instance.pk)
        if existente.exists():
            raise serializers.ValidationError("Ya existe una cuenta con ese correo.")
        return v.strip()

    def create(self, d):
        password = d.pop("password", None)
        return Usuario.objects.create_user(d.pop("correo"), d.pop("nombre"), password, **d)

    def update(self, instance, d):
        password = d.pop("password", None)
        for k, v in d.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RolSerializer(serializers.ModelSerializer):
    permisos = serializers.SerializerMethodField()

    class Meta:
        model = Rol
        fields = ["id", "nombre", "descripcion", "permisos"]

    def get_permisos(self, rol):
        from .models import RolPermiso
        return sorted(RolPermiso.objects.filter(rol=rol).values_list("permiso__codigo", flat=True))


PermisoSerializer = crear_serializador(Permiso, "PermisoSerializer")


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()
