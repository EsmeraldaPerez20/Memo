"""Diagnostico y seguimiento del conocimiento (RF-21 a RF-25).

Modelo de Knowledge Tracing bayesiano simple (BKT): cada respuesta actualiza la probabilidad de que el
estudiante domine el tema. Una dificultad se marca cuando el estudiante falla el mismo tema en
'umbral_alerta_errores' actividades distintas (3 por defecto, configuraciones_sistema).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from . import configuracion, notificaciones

P_INICIAL, P_APRENDE, P_ADIVINA, P_ERROR = 0.30, 0.12, 0.20, 0.10


def _bkt(p, correcta):
    if correcta:
        post = p * (1 - P_ERROR) / (p * (1 - P_ERROR) + (1 - p) * P_ADIVINA)
    else:
        post = p * P_ERROR / (p * P_ERROR + (1 - p) * (1 - P_ADIVINA))
    return post + (1 - post) * P_APRENDE


def nivel_dominio(p, intentos):
    if intentos == 0:
        return "no_iniciado"
    return "bajo" if p < 0.35 else "medio" if p < 0.65 else "alto" if p < 0.85 else "dominado"


def nivel_dificultad(p):
    return "alta" if p < 0.30 else "media" if p < 0.50 else "baja"


def actualizar_tras_intento(intento):
    """Actualiza progreso, dificultades, alertas y metas despues de finalizar una actividad."""
    from apps.diagnostico.models import Dificultad, DificultadEvidencia, Progreso
    from apps.evaluaciones.models import Respuesta
    usuario = intento.usuario
    por_tema = defaultdict(list)
    for r in Respuesta.objects.filter(intento=intento).select_related("pregunta"):
        por_tema[r.pregunta.tema_id].append(r)
    umbral = int(configuracion.obtener("umbral_alerta_errores", 3))
    nuevas_alertas = []
    for tema_id, rs in por_tema.items():
        prog = Progreso.objects.filter(usuario=usuario, tema_id=tema_id).first() or Progreso.objects.create(usuario=usuario, tema_id=tema_id)
        p = float(prog.probabilidad_dominio) if prog.probabilidad_dominio is not None else P_INICIAL
        aciertos = errores = 0
        for r in rs:
            if r.es_correcta is None:
                continue
            p = _bkt(p, r.es_correcta)
            aciertos += 1 if r.es_correcta else 0
            errores += 0 if r.es_correcta else 1
        prog.aciertos += aciertos
        prog.errores += errores
        prog.intentos_totales += aciertos + errores
        prog.tiempo_total_segundos += sum(r.tiempo_segundos or 0 for r in rs)
        prog.probabilidad_dominio = Decimal(str(round(p, 4)))
        prog.porcentaje = Decimal(str(round(p * 100, 2)))
        prog.nivel_dominio = nivel_dominio(p, prog.intentos_totales)
        prog.save()
        # --- dificultades: errores del mismo tema en actividades distintas (RF-21, RF-22).
        # Solo cuentan los errores posteriores a la ultima dificultad superada, para poder cerrar el ciclo.
        errores = Respuesta.objects.filter(intento__usuario=usuario, pregunta__tema_id=tema_id, es_correcta=False)
        previa = Dificultad.objects.filter(usuario=usuario, tema_id=tema_id, estado="superada").order_by("-fecha_superacion").first()
        if previa is not None and previa.fecha_superacion:
            errores = errores.filter(fecha_respuesta__gt=previa.fecha_superacion)
        relevantes = errores.values("intento__actividad_id").distinct().count()
        activa = Dificultad.objects.filter(usuario=usuario, tema_id=tema_id, estado="activa").first()
        if activa is not None and p >= 0.80:
            activa.estado, activa.fecha_superacion = "superada", timezone.now()
            activa.save()
        elif relevantes >= umbral:
            if activa is None:
                activa = Dificultad.objects.create(usuario=usuario, tema_id=tema_id, nivel=nivel_dificultad(p), errores_relevantes=relevantes)
            else:
                activa.nivel, activa.errores_relevantes = nivel_dificultad(p), relevantes
            if not activa.alerta_generada:
                activa.alerta_generada = True
                nuevas_alertas.append(activa)
            activa.save()
            ya = set(DificultadEvidencia.objects.filter(dificultad=activa).values_list("respuesta_id", flat=True))
            for r in errores.exclude(pk__in=ya):                           # evidencia: todos los errores que originaron la dificultad (RF-24)
                DificultadEvidencia.objects.create(dificultad=activa, respuesta=r)
    for dif in nuevas_alertas:
        notificaciones.notificar(usuario, "recomendacion", f"Detectamos dificultad en {dif.tema.nombre}",
                                 "Has fallado este tema en varias actividades. Te preparamos recomendaciones para reforzarlo.")
    actualizar_metas(usuario)


def actualizar_metas(usuario):
    """Recalcula el avance de las metas activas (RF-41)."""
    from apps.diagnostico.models import Progreso
    from apps.evaluaciones.models import Intento
    from apps.planificacion.models import Meta
    for meta in Meta.objects.filter(usuario=usuario, estado="activa"):
        filtro_tema = Q(tema=meta.tema) if meta.tema_id else Q()
        if meta.materia_id:
            filtro_tema &= Q(tema__unidad__materia_id=meta.materia_id)
        intentos = Intento.objects.filter(usuario=usuario, estado="finalizado")
        if meta.materia_id:
            intentos = intentos.filter(actividad__materia_id=meta.materia_id)
        if meta.indicador == "calificacion_minima":
            valor = max([float(i.calificacion or 0) for i in intentos], default=0)
        elif meta.indicador == "temas_dominados":
            valor = Progreso.objects.filter(filtro_tema, usuario=usuario, nivel_dominio__in=("alto", "dominado")).count()
        elif meta.indicador == "actividades_completadas":
            valor = intentos.count()
        elif meta.indicador == "horas_estudio":
            valor = round((intentos.aggregate(s=Sum("tiempo_segundos"))["s"] or 0) / 3600, 2)
        else:
            continue
        meta.valor_actual = Decimal(str(valor))
        if meta.valor_actual >= meta.valor_objetivo:
            meta.estado = "cumplida"
            notificaciones.notificar(usuario, "avance", "¡Meta cumplida!", meta.titulo)
        meta.save()
