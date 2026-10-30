"""Modelos de la app documentos.

Generados con tools/gen_models.py a partir de memo_schema.sql. Son managed = False:
las tablas las crea el SQL (Supabase), Django solo las lee y escribe.
"""
from decimal import Decimal  # noqa: F401

from django.db import models
from django.db.models import Value  # noqa: F401
from django.db.models.functions import Now  # noqa: F401
from pgvector.django import VectorField  # noqa: F401


class Documento(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="usuario_id")
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id", null=True, blank=True)
    nombre = models.CharField(max_length=255)
    archivo_url = models.CharField(max_length=500)
    tipo_archivo = models.CharField(max_length=10, choices=[("pdf", "pdf"), ("docx", "docx"), ("pptx", "pptx"), ("txt", "txt"), ("png", "png"), ("jpg", "jpg")])
    tamano_bytes = models.BigIntegerField()
    estado_analisis = models.CharField(max_length=12, choices=[("pendiente", "pendiente"), ("procesando", "procesando"), ("completado", "completado"), ("error", "error")], db_default=Value('pendiente'), blank=True)
    fecha_analisis = models.DateTimeField(null=True, blank=True)
    fecha_subida = models.DateTimeField(db_default=Now(), blank=True)
    fecha_eliminacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "documentos"

    def __str__(self):
        return str(self.nombre)[:60]


class DocumentoTema(models.Model):
    documento = models.OneToOneField("documentos.Documento", models.DO_NOTHING, db_column="documento_id", primary_key=True, related_name="+")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id")
    sugerido_por_ia = models.BooleanField(db_default=Value(True), blank=True)
    confirmado = models.BooleanField(db_default=Value(False), blank=True)

    class Meta:
        managed = False
        db_table = "documento_temas"
        unique_together = (('documento', 'tema'),)

    def __str__(self):
        return f"DocumentoTema {self.pk}"


class ElementoDocumento(models.Model):
    id = models.BigAutoField(primary_key=True)
    documento = models.ForeignKey("documentos.Documento", models.DO_NOTHING, db_column="documento_id")
    tipo = models.CharField(max_length=15, choices=[("resumen", "resumen"), ("concepto", "concepto"), ("definicion", "definicion"), ("palabra_clave", "palabra_clave"), ("pregunta", "pregunta"), ("ejercicio", "ejercicio"), ("tema", "tema")])
    titulo = models.CharField(max_length=200, null=True, blank=True)
    contenido = models.TextField()
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "elementos_documento"

    def __str__(self):
        return str(self.titulo)[:60]


class Material(models.Model):
    id = models.BigAutoField(primary_key=True)
    materia = models.ForeignKey("academico.Materia", models.DO_NOTHING, db_column="materia_id")
    tema = models.ForeignKey("academico.Tema", models.DO_NOTHING, db_column="tema_id", null=True, blank=True)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(null=True, blank=True)
    archivo_url = models.CharField(max_length=500)
    tipo_archivo = models.CharField(max_length=10, choices=[("pdf", "pdf"), ("docx", "docx"), ("pptx", "pptx"), ("txt", "txt"), ("png", "png"), ("jpg", "jpg")])
    tamano_bytes = models.BigIntegerField()
    subido_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="subido_por", related_name="materiales_subido_por")
    estado = models.CharField(max_length=20, choices=[("pendiente", "pendiente"), ("aprobado", "aprobado"), ("rechazado", "rechazado")], db_default=Value('pendiente'), blank=True)
    revisado_por = models.ForeignKey("usuarios.Usuario", models.DO_NOTHING, db_column="revisado_por", related_name="materiales_revisado_por", null=True, blank=True)
    comentarios_revision = models.TextField(null=True, blank=True)
    fecha_revision = models.DateTimeField(null=True, blank=True)
    fecha_publicacion = models.DateTimeField(null=True, blank=True)
    fecha_subida = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "materiales"

    def __str__(self):
        return str(self.titulo)[:60]


class Fragmento(models.Model):
    id = models.BigAutoField(primary_key=True)
    documento = models.ForeignKey("documentos.Documento", models.DO_NOTHING, db_column="documento_id", null=True, blank=True)
    material = models.ForeignKey("documentos.Material", models.DO_NOTHING, db_column="material_id", null=True, blank=True)
    orden = models.IntegerField()
    num_pagina = models.IntegerField(null=True, blank=True)
    contenido = models.TextField()
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    fecha_creacion = models.DateTimeField(db_default=Now(), blank=True)

    class Meta:
        managed = False
        db_table = "fragmentos"

    def __str__(self):
        return str(self.contenido)[:60]
