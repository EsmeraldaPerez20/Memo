"""Modelos de la app evaluaciones.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401


class BancoPregunta(models.Model):
    id = models.BigAutoField(primary_key=True)
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id")
    documento = models.ForeignKey("documentos.Documento", models.DO_NOTHING, db_column="documento_id", null=True, blank=True)
    pregunta_base = models.ForeignKey("evaluaciones.BancoPregunta", models.DO_NOTHING, db_column="pregunta_base_id", related_name="banco_preguntas_pregunta_base", null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=[("opcion_multiple", "opcion_multiple"), ("verdadero_falso", "verdadero_falso"), ("relacion_columnas", "relacion_columnas"), ("completar_espacios", "completar_espacios"), ("abierta", "abierta"), ("problema_matematico", "problema_matematico"), ("practico", "practico")])
    enunciado = models.TextField()
    opciones = models.JSONField(null=True, blank=True)
    respuesta_correcta = models.TextField()
    explicacion = models.TextField(null=True, blank=True)
    dificultad = models.CharField(max_length=10, choices=[("baja", "baja"), ("media", "media"), ("alta", "alta")])
    origen = models.CharField(max_length=10, choices=[("ia", "ia"), ("docente", "docente")], db_default=Value('ia'), blank=True)
    validada = models.BooleanField(db_default=Value(False), blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "banco_preguntas"

    def __str__(self):
        return str(self.enunciado)[:60]


class Actividad(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id")
    tipo = models.CharField(max_length=10, choices=[("ejercicio", "ejercicio"), ("quiz", "quiz"), ("simulacro", "simulacro"), ("examen", "examen")])
    titulo = models.CharField(max_length=200)
    dificultad = models.CharField(max_length=10, choices=[("baja", "baja"), ("media", "media"), ("alta", "alta"), ("adaptativa", "adaptativa")])
    num_preguntas = models.SmallIntegerField()
    limite_tiempo_min = models.SmallIntegerField(null=True, blank=True)
    generada_por = models.CharField(max_length=10, choices=[("ia", "ia"), ("docente", "docente")], db_default=Value('ia'), blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "actividades"

    def __str__(self):
        return str(self.titulo)[:60]


class ActividadTema(models.Model):
    actividad = models.OneToOneField("evaluaciones.Actividad", models.DO_NOTHING, db_column="actividad_id", primary_key=True, related_name="+")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id")

    class Meta:
        managed = False
        db_table = "actividad_temas"
        unique_together = (('actividad', 'tema'),)

    def __str__(self):
        return f"ActividadTema {self.pk}"


class ActividadPregunta(models.Model):
    actividad = models.OneToOneField("evaluaciones.Actividad", models.DO_NOTHING, db_column="actividad_id", primary_key=True, related_name="+")
    pregunta = models.ForeignKey("evaluaciones.BancoPregunta", models.DO_NOTHING, db_column="pregunta_id")
    orden = models.SmallIntegerField(db_default=Value(1), blank=True)

    class Meta:
        managed = False
        db_table = "actividad_preguntas"
        unique_together = (('actividad', 'pregunta'),)

    def __str__(self):
        return str(self.pregunta)[:60]


class Intento(models.Model):
    id = models.BigAutoField(primary_key=True)
    actividad = models.ForeignKey("evaluaciones.Actividad", models.DO_NOTHING, db_column="actividad_id")
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    numero_intento = models.SmallIntegerField(db_default=Value(1), blank=True)
    estado = models.CharField(max_length=12, choices=[("en_curso", "en_curso"), ("finalizado", "finalizado"), ("expirado", "expirado")], db_default=Value('en_curso'), blank=True)
    calificacion = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tiempo_segundos = models.IntegerField(null=True, blank=True)
    retroalimentacion = models.TextField(null=True, blank=True)
    fecha_inicio = models.DateTimeField(db_default=Now(), blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "intentos"
        unique_together = (('actividad', 'usuario', 'numero_intento'),)

    def __str__(self):
        return f"Intento {self.pk}"


class Respuesta(models.Model):
    id = models.BigAutoField(primary_key=True)
    intento = models.ForeignKey("evaluaciones.Intento", models.DO_NOTHING, db_column="intento_id")
    pregunta = models.ForeignKey("evaluaciones.BancoPregunta", models.DO_NOTHING, db_column="pregunta_id")
    respuesta_usuario = models.TextField(null=True, blank=True)
    es_correcta = models.BooleanField(null=True, blank=True)
    puntaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    retroalimentacion = models.TextField(null=True, blank=True)
    tiempo_segundos = models.IntegerField(null=True, blank=True)
    fecha_respuesta = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "respuestas"
        unique_together = (('intento', 'pregunta'),)

    def __str__(self):
        return str(self.pregunta)[:60]
