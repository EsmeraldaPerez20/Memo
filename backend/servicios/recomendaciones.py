"""Recomendaciones y planes de estudio (RF-37 a RF-40) a partir de las dificultades detectadas."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import notificaciones


def generar_recomendaciones(usuario):
    from apps.diagnostico.models import Dificultad
    from apps.documentos.models import DocumentoTema
    from apps.planificacion.models import Recomendacion
    creadas = []
    for dif in Dificultad.objects.filter(usuario=usuario, estado="activa").select_related("tema"):
        abiertas = Recomendacion.objects.filter(usuario=usuario, tema=dif.tema, estado__in=("pendiente", "aceptada", "modificada"))
        existentes = set(abiertas.values_list("tipo", flat=True))
        prioridad = {"alta": "alta", "media": "media", "baja": "baja"}[dif.nivel]
        plantillas = [
            ("repasar_tema", f"Repasa: {dif.tema.nombre}",
             f"Has fallado este tema en {dif.errores_relevantes} actividades. Vuelve a leer tus apuntes y pide al tutor una explicacion sencilla."),
            ("practicar_ejercicios", f"Practica ejercicios de {dif.tema.nombre}",
             "Resuelve un quiz corto de dificultad baja y sube la dificultad cuando aciertes la mayoria."),
        ]
        doc = DocumentoTema.objects.filter(tema=dif.tema, documento__usuario=usuario, documento__fecha_eliminacion__isnull=True).select_related("documento").first()
        if doc:
            plantillas.append(("estudiar_documento", f"Estudia tus apuntes: {doc.documento.nombre}", "Este documento esta relacionado con el tema que te cuesta."))
        for tipo, titulo, descripcion in plantillas:
            if tipo not in existentes:
                creadas.append(Recomendacion.objects.create(usuario=usuario, tema=dif.tema, titulo=titulo, descripcion=descripcion,
                                                            tipo=tipo, prioridad=prioridad, origen="ia"))
    if creadas:
        notificaciones.notificar(usuario, "recomendacion", "Nuevas recomendaciones de estudio", f"Tienes {len(creadas)} recomendaciones nuevas.")
    return creadas


def generar_plan(usuario, tipo="semanal", dias=7):
    """Arma un plan propuesto con las recomendaciones pendientes o aceptadas (RF-38, RF-40)."""
    from apps.planificacion.models import PlanEstudio, PlanEstudioItem, Recomendacion
    orden = {"alta": 0, "media": 1, "baja": 2}
    recs = sorted(Recomendacion.objects.filter(usuario=usuario, estado__in=("pendiente", "aceptada")).order_by("id"), key=lambda r: orden[r.prioridad])
    if not recs:
        raise ValueError("No hay recomendaciones pendientes. Completa actividades para que Memo detecte que reforzar.")
    hoy = timezone.localdate()
    with transaction.atomic():
        plan = PlanEstudio.objects.create(usuario=usuario, titulo="Plan semanal de estudio" if tipo == "semanal" else "Ruta de aprendizaje",
                                          tipo=tipo, generado_por_ia=True, fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=dias - 1))
        PlanEstudioItem.objects.bulk_create([
            PlanEstudioItem(plan=plan, tema=r.tema, recomendacion=r, titulo=r.titulo, fecha_programada=hoy + timedelta(days=i % dias),
                            orden=i + 1, duracion_min=30) for i, r in enumerate(recs)])
    return plan
