"""Modelos de la app administracion.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Notificacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    tipo = models.CharField(max_length=15, choices=[("recomendacion", "recomendacion"), ("recordatorio", "recordatorio"), ("resultado", "resultado"), ("material", "material"), ("avance", "avance")])
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField(null=True, blank=True)
    canal = models.CharField(max_length=10, choices=[("app", "app"), ("correo", "correo"), ("whatsapp", "whatsapp")], db_default=Value('app'), blank=True)
    leida = models.BooleanField(db_default=Value(False), blank=True)
    fecha_programada = models.DateTimeField(null=True, blank=True)
    fecha_envio = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "notificaciones"

    def __str__(self):
        return str(self.titulo)[:60]


class BitacoraAuditoria(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", null=True, blank=True)
    accion = models.CharField(max_length=60)
    entidad = models.CharField(max_length=60, null=True, blank=True)
    entidad_id = models.BigIntegerField(null=True, blank=True)
    detalle = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "bitacora_auditoria"

    def __str__(self):
        return f"BitacoraAuditoria {self.pk}"


class Incidencia(models.Model):
    id = models.BigAutoField(primary_key=True)
    reportada_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="reportada_por", related_name="incidencias_reportada_por", null=True, blank=True)
    asignada_a = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="asignada_a", related_name="incidencias_asignada_a", null=True, blank=True)
    tipo = models.CharField(max_length=15, choices=[("error_sistema", "error_sistema"), ("falla_ia", "falla_ia"), ("seguridad", "seguridad"), ("rendimiento", "rendimiento"), ("otro", "otro")])
    severidad = models.CharField(max_length=10, choices=[("baja", "baja"), ("media", "media"), ("alta", "alta"), ("critica", "critica")], db_default=Value('media'), blank=True)
    descripcion = models.TextField()
    estado = models.CharField(max_length=12, choices=[("abierta", "abierta"), ("en_revision", "en_revision"), ("resuelta", "resuelta"), ("descartada", "descartada")], db_default=Value('abierta'), blank=True)
    fecha_reporte = models.DateTimeField(db_default=Now(), blank=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "incidencias"

    def __str__(self):
        return str(self.descripcion)[:60]


class ConsumoIA(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", null=True, blank=True)
    mensaje = models.ForeignKey("tutor.Mensaje", models.DO_NOTHING, db_column="mensaje_id", null=True, blank=True)
    funcion = models.CharField(max_length=25, choices=[("tutor", "tutor"), ("analisis_documento", "analisis_documento"), ("generacion_ejercicios", "generacion_ejercicios"), ("generacion_quiz", "generacion_quiz"), ("retroalimentacion", "retroalimentacion"), ("embeddings", "embeddings"), ("otro", "otro")])
    proveedor = models.CharField(max_length=30, null=True, blank=True)
    modelo = models.CharField(max_length=60, null=True, blank=True)
    tokens_entrada = models.IntegerField(db_default=Value(0), blank=True)
    tokens_salida = models.IntegerField(db_default=Value(0), blank=True)
    costo_estimado = models.DecimalField(max_digits=10, decimal_places=6, db_default=Value(Decimal("0")), blank=True)
    duracion_ms = models.IntegerField(null=True, blank=True)
    fecha = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "consumo_ia"

    def __str__(self):
        return f"ConsumoIA {self.pk}"


class ConfiguracionSistema(models.Model):
    clave = models.CharField(max_length=80, primary_key=True)
    valor = models.JSONField()
    descripcion = models.CharField(max_length=250, null=True, blank=True)
    actualizado_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="actualizado_por", null=True, blank=True)
    fecha_actualizacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "configuraciones_sistema"

    def __str__(self):
        return str(self.clave)[:60]
