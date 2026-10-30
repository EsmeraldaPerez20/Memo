"""Generacion, resolucion y calificacion de ejercicios, quizzes y simulacros (RF-26 a RF-36).

Formato de las preguntas (banco_preguntas), igual que el COMMENT del schema:
  opcion_multiple    opciones [{"id":"a","texto":".."}...]            respuesta_correcta "a"
  verdadero_falso    opciones NULL                                    "verdadero" | "falso"
  relacion_columnas  {"columna_a":[{id,texto}],"columna_b":[{id,texto}]}  '{"1":"b"}'
  completar_espacios opciones NULL (enunciado con ___)               '["resp1","resp2"]'
  abierta / practico opciones NULL                                    respuesta modelo o criterios
  problema_matematico opciones NULL                                   resultado final
Puntaje de cada respuesta: 0.00 a 1.00. Calificacion del intento: 0 a 100.
"""
import json
import math
import re
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from . import diagnostico, ia

TIPOS_PREGUNTA = ("opcion_multiple", "verdadero_falso", "relacion_columnas", "completar_espacios",
                  "abierta", "problema_matematico", "practico")
TIPOS_POR_DEFECTO = ["opcion_multiple", "verdadero_falso", "completar_espacios", "abierta"]
GRACIA_SEG = 10          # tolerancia de red al validar el tiempo limite en el servidor (RF-34)


class ErrorEvaluacion(Exception):
    """Error de reglas de negocio; las vistas lo convierten en 400."""


# ------------------------------------------------------------------ generacion
def nivel_por_progreso(usuario, tema):
    """Dificultad adaptativa segun el dominio del estudiante (RF-29)."""
    from apps.diagnostico.models import Progreso
    prog = Progreso.objects.filter(usuario=usuario, tema=tema).first()
    p = float(prog.probabilidad_dominio) if prog and prog.probabilidad_dominio is not None else diagnostico.P_INICIAL
    return "baja" if p < 0.40 else "media" if p < 0.75 else "alta"


def _contexto(usuario, temas, limite=6):
    from django.db.models import Q
    from apps.documentos.models import DocumentoTema, Fragmento, Material
    docs = DocumentoTema.objects.filter(tema__in=temas, confirmado=True, documento__usuario=usuario,
                                        documento__fecha_eliminacion__isnull=True).values_list("documento_id", flat=True)
    mats = Material.objects.filter(tema__in=temas, estado="aprobado").values_list("id", flat=True)
    return [f.contenido for f in Fragmento.objects.filter(Q(documento_id__in=list(docs)) | Q(material_id__in=list(mats))).order_by("id")[:limite]]


def _sim_preguntas(tema, n, tipos, contexto):
    """Preguntas de ejemplo para el modo simulado (sin proveedor de IA)."""
    base = contexto[0][:160] if contexto else f"Concepto central de {tema}"
    salida = []
    for i in range(n):
        tipo = tipos[i % len(tipos)]
        if tipo == "opcion_multiple":
            letras = ["a", "b", "c", "d"]
            ok = letras[i % 4]
            textos = [f"Un tema ajeno a {tema}", "Una definicion incorrecta", "Ninguna de las anteriores"]
            opciones = []
            for L in letras:
                opciones.append({"id": L, "texto": base if L == ok else textos.pop(0)})
            salida.append({"tipo": tipo, "enunciado": f"¿Cual describe mejor «{tema}»?", "opciones": opciones,
                           "respuesta_correcta": ok, "explicacion": f"La opcion correcta resume {tema}."})
        elif tipo == "verdadero_falso":
            salida.append({"tipo": tipo, "enunciado": f"Verdadero o falso: «{tema}» forma parte del contenido de la materia.",
                           "opciones": None, "respuesta_correcta": "verdadero", "explicacion": f"{tema} esta incluido en el temario."})
        elif tipo == "completar_espacios":
            salida.append({"tipo": tipo, "enunciado": "El tema que estudias ahora se llama ___.", "opciones": None,
                           "respuesta_correcta": [tema], "explicacion": f"El tema es {tema}."})
        elif tipo == "relacion_columnas":
            salida.append({"tipo": tipo, "enunciado": "Relaciona cada concepto con su descripcion.",
                           "opciones": {"columna_a": [{"id": "1", "texto": tema}, {"id": "2", "texto": "Otro tema"}],
                                        "columna_b": [{"id": "a", "texto": "Tema de otra materia"}, {"id": "b", "texto": base}]},
                           "respuesta_correcta": {"1": "b", "2": "a"}, "explicacion": f"{tema} se relaciona con su descripcion."})
        elif tipo == "problema_matematico":
            salida.append({"tipo": tipo, "enunciado": f"Calcula {i + 2} x 3.", "opciones": None,
                           "respuesta_correcta": str((i + 2) * 3), "explicacion": f"{i + 2} multiplicado por 3 es {(i + 2) * 3}."})
        else:
            salida.append({"tipo": tipo, "enunciado": f"Explica con tus palabras que es «{tema}».", "opciones": None,
                           "respuesta_correcta": base, "explicacion": "Una buena respuesta menciona la idea central del tema."})
    return salida


def _limpiar(p, tipos):
    """Valida y normaliza una pregunta generada por la IA. Devuelve None si no sirve."""
    if not isinstance(p, dict) or p.get("tipo") not in tipos:
        return None
    enunciado = str(p.get("enunciado", "")).strip()
    resp = p.get("respuesta_correcta")
    if not enunciado or resp in (None, "", [], {}):
        return None
    if p["tipo"] in ("relacion_columnas", "completar_espacios") and not isinstance(resp, str):
        resp = json.dumps(resp, ensure_ascii=False)
    opciones = p.get("opciones") if p["tipo"] in ("opcion_multiple", "relacion_columnas") else None
    if p["tipo"] == "opcion_multiple" and not (isinstance(opciones, list) and len(opciones) >= 2):
        return None
    return {"tipo": p["tipo"], "enunciado": enunciado, "opciones": opciones, "respuesta_correcta": str(resp).strip(),
            "explicacion": str(p.get("explicacion", "")).strip()}


def _generar_para_tema(usuario, tema, n, tipos, dificultad, funcion):
    from apps.evaluaciones.models import BancoPregunta
    contexto = _contexto(usuario, [tema])
    prompt = (f'Genera {n} preguntas sobre el tema "{tema.nombre}" (materia: {tema.unidad.materia.nombre}). '
              f"Dificultad: {dificultad}. Tipos permitidos: {', '.join(tipos)}.\n"
              + ("Basate en este material:\n" + "\n".join(contexto) + "\n" if contexto else "")
              + 'Devuelve una lista JSON; cada elemento: {"tipo","enunciado","opciones","respuesta_correcta","explicacion"}. '
              'Formatos: opcion_multiple -> opciones [{"id":"a","texto":".."},...] y respuesta_correcta "a"; '
              'verdadero_falso -> opciones null y respuesta "verdadero" o "falso"; relacion_columnas -> opciones '
              '{"columna_a":[{"id":"1","texto":".."}],"columna_b":[{"id":"a","texto":".."}]} y respuesta_correcta un objeto {"1":"b"}; '
              'completar_espacios -> enunciado con ___ por hueco y respuesta_correcta una lista ["..."]; abierta y practico -> '
              'opciones null y respuesta_correcta con la respuesta modelo; problema_matematico -> respuesta_correcta con el resultado final.')
    datos = ia.completar_json(prompt, "Eres un profesor universitario que redacta evaluaciones claras y correctas en espanol.",
                              funcion, usuario, max_tokens=3000, simulacion=lambda: _sim_preguntas(tema.nombre, n, tipos, contexto))
    if isinstance(datos, dict):
        datos = datos.get("preguntas", [])
    limpias = [x for x in (_limpiar(p, tipos) for p in datos) if x][:n]
    return [BancoPregunta.objects.create(tema=tema, dificultad=dificultad, origen="ia", validada=False, **x) for x in limpias]


def generar_actividad(usuario, materia, temas, tipo, dificultad, num_preguntas, limite_tiempo_min=None,
                      adaptativa=False, tipos_pregunta=None, titulo=None):
    from apps.evaluaciones.models import Actividad, ActividadPregunta, ActividadTema, BancoPregunta, Respuesta
    if not temas:
        raise ErrorEvaluacion("Elige al menos un tema.")
    tipos = [t for t in (tipos_pregunta or TIPOS_POR_DEFECTO) if t in TIPOS_PREGUNTA] or TIPOS_POR_DEFECTO
    funcion = "generacion_ejercicios" if tipo == "ejercicio" else "generacion_quiz"
    base, resto = divmod(num_preguntas, len(temas))
    vistas = set(Respuesta.objects.filter(intento__usuario=usuario, pregunta__tema__in=temas).values_list("pregunta_id", flat=True))
    elegidas = []
    with transaction.atomic():
        for i, tema in enumerate(temas):
            n = base + (1 if i < resto else 0)
            if n == 0:
                continue
            nivel = nivel_por_progreso(usuario, tema) if adaptativa else dificultad
            candidatas = list(BancoPregunta.objects.filter(tema=tema, dificultad=nivel, tipo__in=tipos).order_by("-validada", "id"))
            # prefiere preguntas que el estudiante aun no ha resuelto (RF-35)
            usar = ([p for p in candidatas if p.id not in vistas] + [p for p in candidatas if p.id in vistas])[:n]
            if len(usar) < n:
                usar += _generar_para_tema(usuario, tema, n - len(usar), tipos, nivel, funcion)
            elegidas += usar
        if not elegidas:
            raise ErrorEvaluacion("No se pudieron obtener preguntas para esos temas.")
        actividad = Actividad.objects.create(
            usuario=usuario, materia=materia, tipo=tipo, titulo=titulo or f"{tipo.capitalize()} de {materia.nombre}",
            dificultad="adaptativa" if adaptativa else dificultad, num_preguntas=len(elegidas),
            limite_tiempo_min=limite_tiempo_min, generada_por="ia")
        for tema in temas:
            ActividadTema.objects.create(actividad=actividad, tema=tema)
        for orden, p in enumerate(elegidas, 1):
            ActividadPregunta.objects.create(actividad=actividad, pregunta=p, orden=orden)
    return actividad


def preguntas_de(actividad, con_respuestas=False):
    """Preguntas de una actividad en orden. Al estudiante no se le envia la respuesta hasta terminar (RF-33)."""
    from apps.evaluaciones.models import ActividadPregunta
    salida = []
    for ap in ActividadPregunta.objects.filter(actividad=actividad).select_related("pregunta").order_by("orden"):
        p = ap.pregunta
        d = {"id": p.id, "orden": ap.orden, "tipo": p.tipo, "enunciado": p.enunciado, "opciones": p.opciones, "tema": p.tema_id}
        if con_respuestas:
            d.update(respuesta_correcta=p.respuesta_correcta, explicacion=p.explicacion)
        salida.append(d)
    return salida


# ------------------------------------------------------------------ calificacion
def _norm(s):
    return re.sub(r"[^a-z0-9.]+", "", ia.normalizar(s))      # sin acentos, mayusculas, espacios ni signos


def _como_objeto(valor):
    if isinstance(valor, (dict, list)):
        return valor
    try:
        return json.loads(str(valor))
    except ValueError:
        return None


def _sim_abierta(pregunta, texto):
    modelo, dado = set(ia.tokens(pregunta.respuesta_correcta)), set(ia.tokens(texto))
    puntaje = min(1.0, (len(modelo & dado) / max(1, len(modelo))) * 1.5)
    return {"puntaje": round(puntaje, 2), "retroalimentacion": "Tu respuesta cubre los puntos principales." if puntaje >= 0.6
            else "Tu respuesta esta incompleta: revisa los conceptos clave del tema."}


def calificar(pregunta, respuesta, usuario):
    """Devuelve (es_correcta, puntaje 0-1, retroalimentacion)."""
    tipo, correcta = pregunta.tipo, pregunta.respuesta_correcta
    puntaje = 0.0
    if tipo == "opcion_multiple":
        puntaje = 1.0 if _norm(str(respuesta)) == _norm(correcta) else 0.0
    elif tipo == "verdadero_falso":
        def bool_de(x):
            return {"verdadero": True, "true": True, "v": True, "falso": False, "false": False, "f": False}.get(_norm(str(x)))
        puntaje = 1.0 if bool_de(respuesta) is not None and bool_de(respuesta) == bool_de(correcta) else 0.0
    elif tipo == "relacion_columnas":
        esperado, dado = _como_objeto(correcta) or {}, _como_objeto(respuesta)
        if isinstance(dado, dict) and esperado:
            puntaje = sum(1 for k, v in esperado.items() if _norm(str(dado.get(k, ""))) == _norm(str(v))) / len(esperado)
    elif tipo == "completar_espacios":
        esperado, dado = _como_objeto(correcta) or [], _como_objeto(respuesta)
        if isinstance(respuesta, str) and not isinstance(dado, list):
            dado = [respuesta]
        if isinstance(dado, list) and esperado:
            puntaje = sum(1 for a, b in zip(esperado, dado) if _norm(str(a)) == _norm(str(b))) / len(esperado)
    elif tipo == "problema_matematico":
        try:
            puntaje = 1.0 if math.isclose(float(str(respuesta).replace(",", ".")), float(correcta.replace(",", ".")), rel_tol=1e-3, abs_tol=1e-6) else 0.0
        except ValueError:
            puntaje = 1.0 if _norm(str(respuesta)) == _norm(correcta) else 0.0
    else:   # abierta, practico: la IA evalua contra la respuesta modelo
        texto = respuesta if isinstance(respuesta, str) else json.dumps(respuesta, ensure_ascii=False)
        prompt = (f"Pregunta: {pregunta.enunciado}\nRespuesta modelo o criterios: {correcta}\nRespuesta del estudiante: {texto}\n"
                  'Evalua y devuelve JSON {"puntaje": numero entre 0 y 1, "retroalimentacion": "explicacion breve en espanol"}')
        datos = ia.completar_json(prompt, "Eres un profesor justo que evalua respuestas de estudiantes.", "retroalimentacion", usuario,
                                  simulacion=lambda: _sim_abierta(pregunta, texto))
        puntaje = max(0.0, min(1.0, float(datos.get("puntaje", 0))))
        return puntaje >= 0.6, round(puntaje, 2), str(datos.get("retroalimentacion", "")) + (f"\n{pregunta.explicacion}" if pregunta.explicacion else "")
    puntaje = round(puntaje, 2)
    if puntaje >= 1:
        retro = "¡Correcto! " + (pregunta.explicacion or "")
    else:
        retro = f"Respuesta esperada: {correcta}. " + (pregunta.explicacion or "")
        if 0 < puntaje < 1:
            retro = f"Respuesta parcialmente correcta. " + retro
    return puntaje >= 1, puntaje, retro.strip()


# ------------------------------------------------------------------ intentos
def tiempo_agotado(intento):
    limite = intento.actividad.limite_tiempo_min
    return bool(limite) and (timezone.now() - intento.fecha_inicio).total_seconds() > limite * 60 + GRACIA_SEG


def iniciar_intento(actividad, usuario):
    from apps.evaluaciones.models import Intento
    abierto = Intento.objects.filter(actividad=actividad, usuario=usuario, estado="en_curso").first()
    if abierto and not tiempo_agotado(abierto):
        return abierto
    if abierto:
        finalizar(abierto)
    anterior = Intento.objects.filter(actividad=actividad, usuario=usuario).order_by("-numero_intento").first()
    return Intento.objects.create(actividad=actividad, usuario=usuario, numero_intento=(anterior.numero_intento + 1) if anterior else 1,
                                  fecha_inicio=timezone.now())


def responder(intento, pregunta_id, respuesta, tiempo_seg=None):
    from apps.evaluaciones.models import ActividadPregunta, Respuesta
    if intento.estado != "en_curso":
        raise ErrorEvaluacion("Este intento ya termino.")
    if tiempo_agotado(intento):
        finalizar(intento)
        raise ErrorEvaluacion("Se agoto el tiempo de la actividad.")
    ap = ActividadPregunta.objects.filter(actividad=intento.actividad, pregunta_id=pregunta_id).select_related("pregunta").first()
    if ap is None:
        raise ErrorEvaluacion("La pregunta no pertenece a esta actividad.")
    ok, puntaje, retro = calificar(ap.pregunta, respuesta, intento.usuario)
    guardada = respuesta if isinstance(respuesta, str) else json.dumps(respuesta, ensure_ascii=False)
    campos = dict(fecha_respuesta=timezone.now(), respuesta_usuario=guardada, es_correcta=ok, puntaje=Decimal(str(puntaje)), retroalimentacion=retro, tiempo_segundos=tiempo_seg)
    existente = Respuesta.objects.filter(intento=intento, pregunta_id=pregunta_id).first()
    if existente:
        for k, v in campos.items():
            setattr(existente, k, v)
        existente.save()
        return existente
    return Respuesta.objects.create(intento=intento, pregunta_id=pregunta_id, **campos)


def finalizar(intento):
    """Cierra el intento: calcula la calificacion, valida el tiempo y actualiza el diagnostico (RF-31, RF-34, RF-36)."""
    from apps.evaluaciones.models import Respuesta
    if intento.estado != "en_curso":
        return intento
    expirado = tiempo_agotado(intento)
    total = intento.actividad.num_preguntas or 1
    suma = sum(float(r.puntaje or 0) for r in Respuesta.objects.filter(intento=intento))
    ahora = timezone.now()
    intento.estado = "expirado" if expirado else "finalizado"
    intento.calificacion = Decimal(str(round(suma / total * 100, 2)))
    intento.fecha_fin = ahora
    intento.tiempo_segundos = int((ahora - intento.fecha_inicio).total_seconds())
    intento.retroalimentacion = ("Se agoto el tiempo; se calificaron las respuestas enviadas a tiempo. " if expirado else "") \
        + f"Obtuviste {intento.calificacion}/100."
    intento.save()
    diagnostico.actualizar_tras_intento(intento)
    from . import notificaciones
    notificaciones.notificar(intento.usuario, "resultado", f"Resultado: {intento.actividad.titulo}", intento.retroalimentacion)
    return intento
