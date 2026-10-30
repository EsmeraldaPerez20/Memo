"""Modelos de la app diagnostico.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Progreso(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2, db_default=Value(Decimal("0")), blank=True)
    probabilidad_dominio = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    nivel_dominio = models.CharField(max_length=15, choices=[("no_iniciado", "no_iniciado"), ("bajo", "bajo"), ("medio", "medio"), ("alto", "alto"), ("dominado", "dominado")], db_default=Value('no_iniciado'), blank=True)
    intentos_totales = models.IntegerField(db_default=Value(0), blank=True)
    aciertos = models.IntegerField(db_default=Value(0), blank=True)
    errores = models.IntegerField(db_default=Value(0), blank=True)
    tiempo_total_segundos = models.BigIntegerField(db_default=Value(0), blank=True)
    fecha_actualizacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "progreso"
        unique_together = (('usuario', 'tema'),)

    def __str__(self):
        return f"Progreso {self.pk}"


class Dificultad(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id")
    nivel = models.CharField(max_length=10, choices=[("baja", "baja"), ("media", "media"), ("alta", "alta")])
    estado = models.CharField(max_length=10, choices=[("activa", "activa"), ("superada", "superada")], db_default=Value('activa'), blank=True)
    errores_relevantes = models.SmallIntegerField(db_default=Value(0), blank=True)
    alerta_generada = models.BooleanField(db_default=Value(False), blank=True)
    fecha_deteccion = models.DateTimeField(db_default=Now(), blank=True)
    fecha_actualizacion = models.DateTimeField(db_default=Now(), blank=True)
    fecha_superacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "dificultades"

    def __str__(self):
        return f"Dificultad {self.pk}"


class DificultadEvidencia(models.Model):
    dificultad = models.OneToOneField("diagnostico.Dificultad", models.DO_NOTHING, db_column="dificultad_id", primary_key=True, related_name="+")
    respuesta = models.ForeignKey("evaluaciones.Respuesta", models.DO_NOTHING, db_column="respuesta_id")

    class Meta:
        managed = False
        db_table = "dificultad_evidencias"
        unique_together = (('dificultad', 'respuesta'),)

    def __str__(self):
        return f"DificultadEvidencia {self.pk}"
