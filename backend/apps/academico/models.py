"""Modelos de la app academico.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Materia(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(null=True, blank=True)
    activa = models.BooleanField(db_default=Value(True), blank=True)
    creada_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="creada_por", null=True, blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "materias"

    def __str__(self):
        return str(self.nombre)[:60]


class UsuarioMateria(models.Model):
    usuario = models.OneToOneField("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", primary_key=True, related_name="+")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id")
    relacion = models.CharField(max_length=10, choices=[("cursa", "cursa"), ("imparte", "imparte")])
    fecha_alta = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "usuarios_materias"
        unique_together = (('usuario', 'materia', 'relacion'),)

    def __str__(self):
        return f"UsuarioMateria {self.pk}"


class Unidad(models.Model):
    id = models.BigAutoField(primary_key=True)
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id")
    nombre = models.CharField(max_length=150)
    orden = models.SmallIntegerField(db_default=Value(1), blank=True)

    class Meta:
        managed = False
        db_table = "unidades"

    def __str__(self):
        return str(self.nombre)[:60]


class Tema(models.Model):
    id = models.BigAutoField(primary_key=True)
    unidad = models.ForeignKey("academico.Unidad", models.DO_NOTHING, db_column="unidad_id")
    tema_padre = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_padre_id", related_name="temas_tema_padre", null=True, blank=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(null=True, blank=True)
    orden = models.SmallIntegerField(db_default=Value(1), blank=True)

    class Meta:
        managed = False
        db_table = "temas"

    def __str__(self):
        return str(self.nombre)[:60]
