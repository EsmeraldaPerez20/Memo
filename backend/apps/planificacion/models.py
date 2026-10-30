"""Modelos de la app planificacion.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class Recomendacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id", null=True, blank=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(null=True, blank=True)
    tipo = models.CharField(max_length=25, choices=[("repasar_tema", "repasar_tema"), ("practicar_ejercicios", "practicar_ejercicios"), ("estudiar_documento", "estudiar_documento"), ("tecnica_estudio", "tecnica_estudio"), ("otro", "otro")])
    prioridad = models.CharField(max_length=10, choices=[("baja", "baja"), ("media", "media"), ("alta", "alta")], db_default=Value('media'), blank=True)
    estado = models.CharField(max_length=12, choices=[("pendiente", "pendiente"), ("aceptada", "aceptada"), ("modificada", "modificada"), ("rechazada", "rechazada")], db_default=Value('pendiente'), blank=True)
    origen = models.CharField(max_length=10, choices=[("ia", "ia"), ("docente", "docente")], db_default=Value('ia'), blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)
    fecha_respuesta = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "recomendaciones"

    def __str__(self):
        return str(self.titulo)[:60]


class PlanEstudio(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id", related_name="planes_estudio_usuario")
    titulo = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10, choices=[("ruta", "ruta"), ("semanal", "semanal")])
    estado = models.CharField(max_length=12, choices=[("propuesto", "propuesto"), ("activo", "activo"), ("modificado", "modificado"), ("finalizado", "finalizado"), ("descartado", "descartado")], db_default=Value('propuesto'), blank=True)
    generado_por_ia = models.BooleanField(db_default=Value(True), blank=True)
    revisado_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="revisado_por", related_name="planes_estudio_revisado_por", null=True, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "planes_estudio"

    def __str__(self):
        return str(self.titulo)[:60]


class PlanEstudioItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey("planificacion.PlanEstudio", models.DO_NOTHING, db_column="plan_id")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id", null=True, blank=True)
    recomendacion = models.ForeignKey("planificacion.Recomendacion", models.DO_NOTHING, db_column="recomendacion_id", null=True, blank=True)
    titulo = models.CharField(max_length=200)
    fecha_programada = models.DateField(null=True, blank=True)
    orden = models.SmallIntegerField(db_default=Value(1), blank=True)
    duracion_min = models.SmallIntegerField(null=True, blank=True)
    completado = models.BooleanField(db_default=Value(False), blank=True)
    fecha_completado = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "plan_estudio_items"

    def __str__(self):
        return str(self.titulo)[:60]


class Meta(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id", null=True, blank=True)
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id", null=True, blank=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(null=True, blank=True)
    indicador = models.CharField(max_length=25, choices=[("calificacion_minima", "calificacion_minima"), ("temas_dominados", "temas_dominados"), ("actividades_completadas", "actividades_completadas"), ("horas_estudio", "horas_estudio"), ("personalizada", "personalizada")])
    valor_objetivo = models.DecimalField(max_digits=8, decimal_places=2)
    valor_actual = models.DecimalField(max_digits=8, decimal_places=2, db_default=Value(Decimal("0")), blank=True)
    fecha_limite = models.DateField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=[("activa", "activa"), ("cumplida", "cumplida"), ("vencida", "vencida"), ("cancelada", "cancelada")], db_default=Value('activa'), blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "metas"

    def __str__(self):
        return str(self.titulo)[:60]


class Tarea(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id", null=True, blank=True)
    titulo = models.CharField(max_length=200)
    detalle = models.CharField(max_length=300, null=True, blank=True)
    tipo = models.CharField(max_length=10, choices=[("tarea", "tarea"), ("examen", "examen"), ("entrega", "entrega"), ("practica", "practica"), ("repaso", "repaso")], db_default=Value('tarea'), blank=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    completada = models.BooleanField(db_default=Value(False), blank=True)
    fecha_completada = models.DateTimeField(null=True, blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "tareas"

    def __str__(self):
        return str(self.titulo)[:60]
