"""
Modelos de autenticacion de Memo (FourMind).
Copiar como:  backend/apps/usuarios/models.py

Reglas del equipo
  * Usuario basado en AbstractBaseUser (NO AbstractUser y NO PermissionsMixin).
  * db_table = 'usuarios', USERNAME_FIELD = 'correo'.
  * La contrasena se guarda en la columna password_hash.
  * Roles y permisos viven en las tablas roles / permisos / roles_permisos de
    memo_schema.sql. Django no crea tablas puente de grupos ni permisos para el
    usuario, asi no se duplican roles y permisos.
  * managed = False: las tablas las crea memo_schema.sql, no las migraciones.

En settings.py:
    AUTH_USER_MODEL = "usuarios.Usuario"
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone
from decimal import Decimal  # noqa: F401
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Rol(models.Model):
    """roles: estudiante, docente, administrador (RF-03)."""

    id = models.SmallAutoField(primary_key=True)
    nombre = models.CharField(max_length=30, unique=True)
    descripcion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "roles"

    def __str__(self):
        return self.nombre


class Permiso(models.Model):
    """permisos: uno por funcion protegida, ej. 'materiales.aprobar'."""

    id = models.SmallAutoField(primary_key=True)
    codigo = models.CharField(max_length=60, unique=True)
    descripcion = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "permisos"

    def __str__(self):
        return self.codigo


class RolPermiso(models.Model):
    """
    roles_permisos tiene llave primaria compuesta (rol_id, permiso_id).
    Django 5.1 no la soporta: se marca rol como pk solo para CONSULTAR
    (es lo mismo que genera inspectdb). Con Django 5.2 se cambia por
    CompositePrimaryKey("rol_id", "permiso_id").
    """

    rol = models.OneToOneField(
        Rol, models.DO_NOTHING, db_column="rol_id", primary_key=True, related_name="+"
    )
    permiso = models.ForeignKey(
        Permiso, models.DO_NOTHING, db_column="permiso_id", related_name="+"
    )

    class Meta:
        managed = False
        db_table = "roles_permisos"
        unique_together = (("rol", "permiso"),)


class UsuarioManager(BaseUserManager):
    def get_queryset(self):
        return super().get_queryset().select_related("rol")

    def get_by_natural_key(self, correo):
        # El correo no distingue mayusculas (RF-01, RF-02): hay indice unico sobre lower(correo).
        return self.get(correo__iexact=correo.strip())

    def create_user(self, correo, nombre, password=None, **extra):
        if not correo:
            raise ValueError("El correo es obligatorio")
        # El registro publico solo crea estudiantes (RF-03).
        extra.setdefault("rol", Rol.objects.get(nombre="estudiante"))
        usuario = self.model(correo=self.normalize_email(correo.strip()), nombre=nombre, **extra)
        if password:
            usuario.set_password(password)
        else:
            usuario.password = None  # cuenta creada con Google: password_hash NULL
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, correo, nombre, password=None, **extra):
        extra["rol"] = Rol.objects.get(nombre="administrador")
        return self.create_user(correo, nombre, password, **extra)


class Usuario(AbstractBaseUser):
    id = models.BigAutoField(primary_key=True)
    rol = models.ForeignKey(Rol, models.PROTECT, db_column="rol_id", related_name="usuarios")
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100, blank=True, null=True)   # el registro solo exige nombre
    correo = models.EmailField(max_length=150, unique=True)

    # AbstractBaseUser define password y last_login; se mapean a las columnas del schema.
    password = models.CharField("password", max_length=255, blank=True, null=True, db_column="password_hash")
    last_login = models.DateTimeField("ultimo acceso", blank=True, null=True, db_column="ultimo_acceso")
    is_active = models.BooleanField(default=True, db_column="activo")

    google_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)   # formato internacional: +52...
    aviso_privacidad_version = models.CharField(max_length=20, blank=True, null=True)
    aviso_privacidad_aceptado_en = models.DateTimeField(blank=True, null=True)
    fecha_registro = models.DateTimeField(default=timezone.now)
    fecha_actualizacion = models.DateTimeField(default=timezone.now)   # la actualiza un trigger de la base

    USERNAME_FIELD = "correo"
    EMAIL_FIELD = "correo"
    REQUIRED_FIELDS = ["nombre"]

    objects = UsuarioManager()

    class Meta:
        managed = False
        db_table = "usuarios"

    def __str__(self):
        return f"{self.nombre} <{self.correo}>"

    def get_full_name(self):
        return f"{self.nombre} {self.apellido or ''}".strip()

    def get_short_name(self):
        return self.nombre

    # ---- cuentas de Google: password_hash NULL ----
    def check_password(self, raw_password):
        # Con password NULL, Django 5.1 lanza TypeError en vez de rechazar el login.
        # Una cuenta creada con Google no puede entrar con contrasena.
        if not self.password:
            return False
        return super().check_password(raw_password)

    def has_usable_password(self):
        return bool(self.password) and super().has_usable_password()

    # ---- roles y permisos propios de Memo (tablas roles / permisos / roles_permisos) ----
    @property
    def es_estudiante(self):
        return self.rol.nombre == "estudiante"

    @property
    def es_docente(self):
        return self.rol.nombre == "docente"

    @property
    def es_administrador(self):
        return self.rol.nombre == "administrador"

    def permisos_codigos(self):
        """Codigos de permiso del rol; se consulta una sola vez por peticion."""
        if not hasattr(self, "_permisos_cache"):
            self._permisos_cache = set(
                RolPermiso.objects.filter(rol_id=self.rol_id).values_list("permiso__codigo", flat=True))
        return self._permisos_cache

    def tiene_permiso(self, codigo):
        """True si el rol del usuario tiene el permiso, ej. usuario.tiene_permiso('materiales.aprobar')."""
        return codigo in self.permisos_codigos()

    # ---- necesario para que el admin de Django funcione sin PermissionsMixin ----
    @property
    def is_staff(self):
        return self.is_active and self.es_administrador

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff


class PerfilAcademico(models.Model):
    usuario = models.OneToOneField("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", primary_key=True, related_name="+")
    carrera = models.CharField(max_length=150, null=True, blank=True)
    semestre = models.SmallIntegerField(null=True, blank=True)
    institucion = models.CharField(max_length=200, null=True, blank=True)
    nivel_academico = models.CharField(max_length=15, choices=[("basico", "basico"), ("intermedio", "intermedio"), ("avanzado", "avanzado")], db_default=Value('basico'), blank=True)
    fecha_actualizacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "perfiles_academicos"

    def __str__(self):
        return f"PerfilAcademico {self.pk}"


class TokenRecuperacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    token_hash = models.CharField(max_length=255)
    expira_en = models.DateTimeField()
    usado = models.BooleanField(db_default=Value(False), blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "tokens_recuperacion"

    def __str__(self):
        return f"TokenRecuperacion {self.pk}"


class PreferenciaUsuario(models.Model):
    usuario = models.OneToOneField("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", primary_key=True, related_name="+")
    modo_oscuro = models.BooleanField(db_default=Value(False), blank=True)
    tamano_letra = models.SmallIntegerField(db_default=Value(16), blank=True)
    lectura_texto = models.BooleanField(db_default=Value(False), blank=True)
    alto_contraste = models.BooleanField(db_default=Value(False), blank=True)
    notif_recomendaciones = models.BooleanField(db_default=Value(True), blank=True)
    notif_recordatorios = models.BooleanField(db_default=Value(True), blank=True)
    notif_resultados = models.BooleanField(db_default=Value(True), blank=True)
    notif_materiales = models.BooleanField(db_default=Value(True), blank=True)
    notif_avances = models.BooleanField(db_default=Value(True), blank=True)
    canal_app = models.BooleanField(db_default=Value(True), blank=True)
    canal_correo = models.BooleanField(db_default=Value(False), blank=True)
    canal_whatsapp = models.BooleanField(db_default=Value(False), blank=True)
    fecha_actualizacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "preferencias_usuario"

    def __str__(self):
        return f"PreferenciaUsuario {self.pk}"
