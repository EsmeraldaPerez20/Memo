"""Modelos de la app tutor.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Conversacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id", null=True, blank=True)
    documento = models.ForeignKey("documentos.Documento", models.DO_NOTHING, db_column="documento_id", null=True, blank=True)
    titulo = models.CharField(max_length=200, null=True, blank=True)
    guardada = models.BooleanField(db_default=Value(False), blank=True)
    fecha_inicio = models.DateTimeField(db_default=Now(), blank=True)
    fecha_ultima_actividad = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "conversaciones"

    def __str__(self):
        return str(self.titulo)[:60]


class Mensaje(models.Model):
    id = models.BigAutoField(primary_key=True)
    conversacion = models.ForeignKey("tutor.Conversacion", models.DO_NOTHING, db_column="conversacion_id")
    emisor = models.CharField(max_length=10, choices=[("estudiante", "estudiante"), ("ia", "ia")])
    contenido = models.TextField()
    modo_explicacion = models.CharField(max_length=15, choices=[("normal", "normal"), ("sencilla", "sencilla"), ("detallada", "detallada"), ("otro_ejemplo", "otro_ejemplo")], db_default=Value('normal'), blank=True)
    advertencia_ia = models.BooleanField(db_default=Value(False), blank=True)
    fecha_envio = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "mensajes"

    def __str__(self):
        return str(self.contenido)[:60]


class MensajeFuente(models.Model):
    mensaje = models.OneToOneField("tutor.Mensaje", models.DO_NOTHING, db_column="mensaje_id", primary_key=True, related_name="+")
    fragmento = models.ForeignKey("documentos.Fragmento", models.DO_NOTHING, db_column="fragmento_id")
    relevancia = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "mensaje_fuentes"
        unique_together = (('mensaje', 'fragmento'),)

    def __str__(self):
        return f"MensajeFuente {self.pk}"


class ReporteIA(models.Model):
    id = models.BigAutoField(primary_key=True)
    mensaje = models.ForeignKey("tutor.Mensaje", models.DO_NOTHING, db_column="mensaje_id", null=True, blank=True)
    contenido_reportado = models.TextField()
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", related_name="reportes_ia_usuario")
    motivo = models.CharField(max_length=15, choices=[("incorrecta", "incorrecta"), ("incompleta", "incompleta"), ("inapropiada", "inapropiada"), ("otro", "otro")])
    comentario = models.TextField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=[("abierto", "abierto"), ("revisado", "revisado"), ("descartado", "descartado")], db_default=Value('abierto'), blank=True)
    revisado_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="revisado_por", related_name="reportes_ia_revisado_por", null=True, blank=True)
    fecha_reporte = models.DateTimeField(db_default=Now(), blank=True)
    fecha_revision = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "reportes_ia"

    def __str__(self):
        return f"ReporteIA {self.pk}"
