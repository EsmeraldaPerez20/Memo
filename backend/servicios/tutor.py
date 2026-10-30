"""Tutor virtual (RF-06 a RF-12, RF-53): responde con base en los apuntes y materiales del estudiante."""
from django.conf import settings

from . import ia, rag

INSTRUCCION_MODO = {
    "normal": "",
    "sencilla": "Explica de forma muy sencilla, con palabras cotidianas y una analogia breve.",
    "detallada": "Explica con detalle y rigor: definiciones, pasos y un ejemplo resuelto.",
    "otro_ejemplo": "Da un ejemplo DISTINTO a los que ya aparecen en la conversacion.",
}
FRASES_DUDA = ("no tengo informacion", "no cuento con informacion", "no estoy seguro", "no encuentro informacion", "no puedo asegurar")


def _sistema(nivel, modo, validos):
    contexto = "\n".join(
        f"[{i}] ({(f.documento.nombre if f.documento_id else f.material.titulo)}"
        f"{', p. ' + str(f.num_pagina) if f.num_pagina else ''}) {f.contenido}" for i, (f, _, _) in enumerate(validos, 1))
    return ("Eres Memo, un tutor virtual academico para estudiantes universitarios. Responde SIEMPRE en espanol.\n"
            f"Nivel del estudiante: {nivel}. {INSTRUCCION_MODO.get(modo, '')}\n"
            "Reglas:\n- Basa tu respuesta en el CONTEXTO cuando exista y cita las fuentes como [1], [2].\n"
            "- Si el contexto no contiene la informacion, dilo con claridad y no inventes datos.\n"
            "- Si no estas seguro de algo, indicalo. Guia al estudiante para que razone; no resuelvas por el solo tareas.\n"
            f"CONTEXTO:\n{contexto or '(sin contexto: no se encontraron apuntes ni materiales relacionados)'}")


def _historial(conversacion, excluir_id, contenido):
    """Mensajes previos con la alternancia usuario/asistente que exigen los proveedores."""
    from apps.tutor.models import Mensaje
    previos = Mensaje.objects.filter(conversacion=conversacion).exclude(pk=excluir_id).order_by("-id")[:10]
    msgs = []
    for m in reversed(list(previos)):
        rol = "user" if m.emisor == "estudiante" else "assistant"
        if msgs and msgs[-1]["role"] == rol:
            msgs[-1]["content"] += "\n" + m.contenido
        else:
            msgs.append({"role": rol, "content": m.contenido})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1]["content"] += "\n" + contenido
    else:
        msgs.append({"role": "user", "content": contenido})
    return msgs


def _simulada(validos, modo):
    if not validos:
        return ("No encuentro informacion sobre esto en tus apuntes ni en los materiales de tu materia, "
                "asi que no puedo asegurarte la respuesta. Sube un documento relacionado o reformula la pregunta.")
    prefijo = {"sencilla": "En palabras simples: ", "detallada": "Con detalle: ", "otro_ejemplo": "Otro ejemplo: "}.get(modo, "")
    extractos = " ".join(f"{f.contenido[:220]} [{i}]" for i, (f, _, _) in enumerate(validos[:2], 1))
    return f"{prefijo}Segun tus fuentes: {extractos}"


def responder(conversacion, usuario, contenido, modo="normal"):
    """Guarda la pregunta, busca contexto, llama a la IA y guarda la respuesta con sus fuentes. Devuelve el mensaje de la IA."""
    from apps.tutor.models import Mensaje, MensajeFuente
    from apps.usuarios.models import PerfilAcademico
    pregunta = Mensaje.objects.create(conversacion=conversacion, emisor="estudiante", contenido=contenido, modo_explicacion=modo)
    encontrados = rag.buscar(usuario, contenido, documento=conversacion.documento, materia=conversacion.materia)
    limite = 0.99 if settings.EMBEDDINGS_PROVEEDOR == "simulado" else settings.RAG_DISTANCIA_MAXIMA
    validos = [r for r in encontrados if r[1] <= limite]
    perfil = PerfilAcademico.objects.filter(usuario=usuario).first()
    resp = ia.completar(_historial(conversacion, pregunta.pk, contenido), system=_sistema(perfil.nivel_academico if perfil else "basico", modo, validos),
                        funcion="tutor", usuario=usuario, simulacion=lambda: _simulada(validos, modo))
    duda = (not validos) or any(f in ia.normalizar(resp.texto) for f in FRASES_DUDA)     # RF-12, RNF-23
    respuesta = Mensaje.objects.create(conversacion=conversacion, emisor="ia", contenido=resp.texto, modo_explicacion=modo, advertencia_ia=duda)
    MensajeFuente.objects.bulk_create([
        MensajeFuente(mensaje=respuesta, fragmento=f, relevancia=round(max(0.0, min(1.0, 1 - d)), 4)) for f, d, _ in validos])
    if resp.consumo is not None:
        resp.consumo.mensaje = respuesta
        resp.consumo.save(update_fields=["mensaje"])
    if not conversacion.titulo:
        conversacion.titulo = contenido[:60]
        conversacion.save(update_fields=["titulo"])
    return respuesta


def fuentes_de(mensaje):
    """Fuentes que respaldan una respuesta de la IA (RF-53)."""
    from apps.tutor.models import MensajeFuente
    salida = []
    for mf in MensajeFuente.objects.filter(mensaje=mensaje).select_related("fragmento__documento", "fragmento__material"):
        f = mf.fragmento
        salida.append({
            "fragmento_id": f.id, "tipo": "documento" if f.documento_id else "material",
            "nombre": f.documento.nombre if f.documento_id else f.material.titulo,
            "pagina": f.num_pagina, "extracto": f.contenido[:240], "relevancia": float(mf.relevancia or 0)})
    return salida
